"""AWS CDK stack provisioning VPC, RDS PostgreSQL (serverless v2) and Secrets Manager secret."""
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as sm,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_cognito as cognito,
)
import aws_cdk.aws_apprunner_alpha as apprunner
from constructs import Construct
import os


class GreatFitInfraStack(Stack):
    """Infrastructure stack for Great Fit production deployment."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # VPC across 2 AZs with public + isolated subnets
        vpc = ec2.Vpc(
            self, "great-fit-vpc",
            max_azs=2,
            nat_gateways=1,                    # shared NAT
            subnet_configuration=[
                ec2.SubnetConfiguration(       # 10.0.0.0/24 & 10.0.1.0/24
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(       # 10.0.2.0/24 & 10.0.3.0/24
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(       # 10.0.4.0/24 & 10.0.5.0/24
                    name="private-egress",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        user_pool_id_secret = sm.Secret.from_secret_name_v2(
            self,
            "UserPoolIdSecretLookup",
            "greatfit/userpool/id"
        )
        user_pool_arn_secret = sm.Secret.from_secret_name_v2(
            self,
            "UserPoolArnSecretLookup",
            "greatfit/userpool/arn"
        )
        user_pool_client_id_secret = sm.Secret.from_secret_name_v2(
            self,
            "UserPoolClientIdSecretLookup",
            "greatfit/userpool/clientid"
        )
        cognito_domain_secret = sm.Secret.from_secret_name_v2(
            self,
            "CognitoDomainSecretLookup",
            "greatfit/cognito/domain"
        )
        db_secret = sm.Secret.from_secret_name_v2(
            self,
            "DBSecretNameLookup",
            "greatfit/db/secret_name"
        )
        db_endpoint_secret = sm.Secret.from_secret_name_v2(
            self,
            "DBEndpointLookup",
            "greatfit/db/endpoint"
        )

        db_username = db_secret.secret_value_from_json("username").to_string()
        db_password = db_secret.secret_value_from_json("password").to_string()
        db_endpoint = db_endpoint_secret.secret_value_from_json("DB_ENDPOINT")
        user_pool_id_string = user_pool_id_secret.secret_value_from_json("GF_USER_POOL_ID").to_string()
        user_pool_arn_string = user_pool_arn_secret.secret_value_from_json("GF_USER_POOL_ARN").to_string()
        user_pool_client_id_string = user_pool_client_id_secret.secret_value_from_json("GF_USER_POOL_CLIENT_ID").to_string()
        cognito_domain_string = cognito_domain_secret.secret_value_from_json("GF_COGNITO_DOMAIN").to_string()

        # --- Container Repository --- #
        ecr_repo = ecr.Repository.from_repository_name(self, "AppRepository", repository_name="great-fit")

        # --- App Runner Service --- #
        openrouter_secret = sm.Secret.from_secret_name_v2(self, "OpenRouterSecretLookup", "greatfit/openrouter/apikey")
        stripe_secret_key = sm.Secret.from_secret_name_v2(self, "StripeSecretKeyLookup", "greatfit/stripe/secretkey")
        stripe_price_id_50_secret = sm.Secret.from_secret_name_v2(self, "StripePrice50Lookup", "greatfit/stripe/price_id_50_credits")

        # Instance role to allow reading secrets
        instance_role = iam.Role(
            self,
            "AppRunnerInstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),
        )
        db_secret.grant_read(instance_role)
        openrouter_secret.grant_read(instance_role)
        stripe_secret_key.grant_read(instance_role)
        stripe_price_id_50_secret.grant_read(instance_role)
        user_pool_id_secret.grant_read(instance_role)
        user_pool_arn_secret.grant_read(instance_role)
        user_pool_client_id_secret.grant_read(instance_role)
        cognito_domain_secret.grant_read(instance_role)
        db_endpoint_secret.grant_read(instance_role)

        # Allow basic Cognito read actions (ListUsers for email lookup etc.)
        instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cognito-idp:ListUsers",
                    "cognito-idp:GetUser",
                ],
                resources=[user_pool_arn_string],
            )
        )

        db_name = "greatfit"
        db_port = "5432"
        database_url = (f"postgresql://{db_username}:{db_password}@{db_endpoint}:{db_port}/{db_name}")

        obs_cfg = apprunner.ObservabilityConfiguration(
            self, "Obs",
            observability_configuration_name="gf-default",
            trace_configuration_vendor=apprunner.TraceConfigurationVendor.AWSXRAY,
        )

        apprunner_service = apprunner.Service(
            self,
            "GreatFitAppRunner",
            source=apprunner.Source.from_ecr(
                repository=ecr_repo,
                tag_or_digest="latest",
                image_configuration=apprunner.ImageConfiguration(
                    port=8080,
                    environment_variables={
                        "DB_HOST": db_endpoint,
                        "DB_PORT": "5432",
                        "DB_NAME": db_name,
                        "DB_USER": db_username,
                        "AWS_REGION": self.region,
                        "COGNITO_USER_POOL_ID": user_pool_id_string,
                        "COGNITO_APP_CLIENT_ID": user_pool_client_id_string,
                        "COGNITO_DOMAIN": cognito_domain_string,
                        "AUTH_BILLING_ENABLED": "true",
                        "DATABASE_URL": database_url,
                    },
                    environment_secrets={
                        "DB_PASSWORD": apprunner.Secret.from_secrets_manager(
                            db_secret, field="password"
                        ),
                        "OPENROUTER_API_KEY": apprunner.Secret.from_secrets_manager(
                            openrouter_secret, field="OPENROUTER_API_KEY"
                        ),
                        "STRIPE_SECRET_KEY": apprunner.Secret.from_secrets_manager(
                            stripe_secret_key, field="STRIPE_SECRET_KEY"
                        ),
                        "STRIPE_PRICE_ID_50_CREDITS": apprunner.Secret.from_secrets_manager(
                            stripe_price_id_50_secret, field="STRIPE_PRICE_ID_50_CREDITS"
                        ),
                    },
                ),
            ),
            cpu=apprunner.Cpu.ONE_VCPU,
            memory=apprunner.Memory.TWO_GB,
            instance_role=instance_role,
            vpc_connector=vpc_connector,
            observability_configuration=obs_cfg
        )

        # Outputs
        CfnOutput(self, "DbEndpoint", value=cluster.cluster_endpoint.hostname)
        CfnOutput(self, "DbSecretArn", value=db_secret.secret_arn)
        CfnOutput(self, "EcrRepoUri", value=ecr_repo.repository_uri)
        CfnOutput(self, "AppRunnerUrl", value=apprunner_service.service_url)

        # Cognito outputs
        CfnOutput(self, "UserPoolId", value=user_pool_id_string)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client_id_string)
        # Ensure this output value matches the domain you are passing to the environment variable
        CfnOutput(self, "CognitoDomainUrl", value=f"https://{cognito_domain_string}")

        # --- Monitoring & Alarms --- #
        # SNS topic for alarm notifications (add your email via env var ALERT_EMAIL or manually)
        alert_email = os.getenv("ALERT_EMAIL")
        topic = sns.Topic(self, "AlarmTopic", display_name="GreatFitAlarms")
        if alert_email:
            topic.add_subscription(subs.EmailSubscription(alert_email))

        # CPU Utilization alarm (>80% for 5 mins)
        cpu_metric = cluster.metric_cpu_utilization().with_(period=Duration.minutes(1))

        cpu_alarm = cw.Alarm(
            self,
            "DbHighCpu",
            metric=cpu_metric,
            evaluation_periods=3,
            datapoints_to_alarm=3,
            threshold=80,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="RDS Aurora CPU > 80%",
            alarm_name="GreatFit-RDS-HighCPU",
            actions_enabled=True,
        )

        # Wire alarm to SNS topic
        cpu_alarm.add_alarm_action(cw_actions.SnsAction(topic))

        # CloudWatch Dashboard
        dashboard = cw.Dashboard(self, "GreatFitDashboard", dashboard_name="GreatFit")
        dashboard.add_widgets(
            cw.GraphWidget(
                title="RDS CPU Utilization",
                left=[cpu_metric],
            )
        )
