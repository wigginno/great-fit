// Ultra simple profile formatter
function formatProfileData(data) {
  if (!data || typeof data !== "object")
    return "<p>No profile data available</p>";

  let html = '<div class="profile-content">';
  // Display skills section first (only special case)
  if (data.skills) {
    html +=
      '<div class="section">' +
      "<h2>Skills</h2>" +
      '<ul class="skills">' +
      data.skills.map((skill) => `<li>${String(skill).trim()}</li>`).join("") +
      "</ul>" +
      "</div>";
  }

  // Process sections array
  if (data.sections) {
    data.sections.forEach((section) => {
      // Section = h2 header
      html += `<div class="section">`;
      html += `<h2>${section.title}</h2>`;
      // Direct entries in section = bullet points
      if (section.entries && section.entries.length > 0) {
        html += "<ul>";
        section.entries.forEach((entry) => {
          html += `<li>${entry}</li>`;
        });
        html += "</ul>";
      }
      // Subsections = h3 headers with indented bullet points
      if (section.subsections && section.subsections.length > 0) {
        section.subsections.forEach((subsection) => {
          html += `<h3>${subsection.title}</h3>`;
          if (subsection.entries && subsection.entries.length > 0) {
            html += '<ul class="indented">';
            subsection.entries.forEach((entry) => {
              html += `<li>${entry}</li>`;
            });
            html += "</ul>";
          }
        });
      }
      html += "</div>"; // Close section
    });
  }
  // Process any remaining top-level fields (except ignored ones)
  const ignoredFields = new Set([
    "id",
    "email",
    "owner_email",
    "contactInformation",
    "skills",
    "sections",
  ]);
  Object.entries(data)
    .filter(
      ([key, value]) =>
        !ignoredFields.has(key) && value !== null && value !== undefined,
    )
    .forEach(([key, value]) => {
      // Format title
      const sectionTitle = key
        .split("_")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");
      html += `<div class="section">`;
      html += `<h2>${sectionTitle}</h2>`;
      // Simple content handling
      if (typeof value === "string") {
        html += `<p>${value}</p>`;
      } else if (Array.isArray(value)) {
        html += "<ul>";
        value.forEach((item) => {
          if (typeof item === "string") {
            html += `<li>${item}</li>`;
          } else if (typeof item === "object") {
            // Just dump first property as text
            const text = Object.values(item)[0] || "Item";
            html += `<li>${text}</li>`;
          }
        });
        html += "</ul>";
      }
      html += "</div>"; // Close section
    });

  html += "</div>"; // Close profile content
  return html;
}

// Add minimal CSS for the simplified structure
document.addEventListener("DOMContentLoaded", function () {
  const style = document.createElement("style");
  style.textContent = `
        .profile-content {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
        }
        .section {
            margin-bottom: 20px;
        }
        h2 {
            font-size: 1.5em;
            margin-bottom: 10px;
            padding-bottom: 4px;
            border-bottom: 1px solid #ddd;
        }
        h3 {
            font-size: 1.2em;
            margin-top: 16px;
            margin-bottom: 10px;
            font-weight: 600;
            color: #2c5282;
            padding-bottom: 3px;
            border-bottom: 1px dotted #cbd5e0;
        }
        ul {
            margin-top: 8px;
            margin-bottom: 15px;
        }
        li {
            margin-bottom: 6px;
            line-height: 1.4;
        }
        ul.indented {
            margin-left: 20px;
        }
        ul.skills {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            list-style: none;
            padding-left: 0;
            margin-top: 12px;
        }
        ul.skills li {
            background-color: #f5f9ff;
            padding: 6px 12px;
            border-radius: 20px;
            display: inline-block;
            font-size: 0.95em;
            color: #2c5282;
            border: 1px solid #cbd5e0;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: all 0.2s ease;
        }
        ul.skills li:hover {
            background-color: #ebf4ff;
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
    `;
  document.head.appendChild(style);
});
