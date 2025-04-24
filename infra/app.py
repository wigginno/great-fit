#!/usr/bin/env python3
"""CDK application entrypoint for Great Fit infrastructure stack."""
import aws_cdk as cdk
from infra_stack import GreatFitInfraStack

app = cdk.App()

GreatFitInfraStack(
    app,
    "GreatFitInfraStack",
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
)

app.synth()
