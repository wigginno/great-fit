// Ultra simple profile formatter
function formatProfileData(data) {
  if (!data || typeof data !== "object" || Object.keys(data).length === 0)
    return "<p>No profile data available</p>";

  // Only if we have actual profile data (skills or sections), add the controls and content
  if (
    !(data.skills && data.skills.length > 0) &&
    !(data.sections && data.sections.length > 0)
  ) {
    return "<p>No profile data available</p>";
  }

  // Add control bar first
  let html = `
    <div class="profile-controls">
      <a href="#" id="expandAllProfile" role="button" class="text-decoration-none text-secondary small me-3">
        <i class="bi bi-arrows-expand me-1"></i>Expand All
      </a>
      <a href="#" id="collapseAllProfile" role="button" class="text-decoration-none text-secondary small">
        <i class="bi bi-arrows-collapse me-1"></i>Collapse All
      </a>
    </div>
    <div class="profile-content">
  `;
  let sectionIndex = 0; // Counter for unique IDs

  // Helper function to generate collapse structure
  const createCollapsibleSection = (title, contentHtml) => {
    const collapseId = `profileSectionCollapse${sectionIndex++}`;
    return (
      `<div class="section">` +
      `<h2 class="collapsible-header" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="true" aria-controls="${collapseId}">` +
      `<span>${title}</span>` + // Wrap title in span for flex layout
      `<span class="collapse-icon">` +
      `<i class="bi bi-chevron-down"></i>` +
      `</span>` +
      `</h2>` +
      `<div class="collapse show" id="${collapseId}">` +
      `<div class="section-content">${contentHtml}</div>` + // Inner div for padding/margin
      `</div>` +
      `</div>`
    );
  };

  // Display skills section first (only special case)
  if (data.skills) {
    const skillsHtml =
      '<ul class="skills">' +
      data.skills.map((skill) => `<li>${String(skill).trim()}</li>`).join("") +
      "</ul>";
    html += createCollapsibleSection("Skills", skillsHtml);
  }

  // Process sections array
  if (data.sections) {
    data.sections.forEach((section) => {
      let sectionContentHtml = "";
      // Direct entries in section = bullet points
      if (section.entries && section.entries.length > 0) {
        sectionContentHtml += "<ul>";
        section.entries.forEach((entry) => {
          sectionContentHtml += `<li>${entry}</li>`;
        });
        sectionContentHtml += "</ul>";
      }
      // Subsections = h3 headers with indented bullet points
      if (section.subsections && section.subsections.length > 0) {
        section.subsections.forEach((subsection) => {
          sectionContentHtml += `<h3>${subsection.title}</h3>`;
          if (subsection.entries && subsection.entries.length > 0) {
            sectionContentHtml += '<ul class="indented">';
            subsection.entries.forEach((entry) => {
              sectionContentHtml += `<li>${entry}</li>`;
            });
            sectionContentHtml += "</ul>";
          }
        });
      }
      html += createCollapsibleSection(section.title, sectionContentHtml);
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
      let sectionContentHtml = "";
      // Simple content handling
      if (typeof value === "string") {
        sectionContentHtml += `<p>${value}</p>`;
      } else if (Array.isArray(value)) {
        sectionContentHtml += "<ul>";
        value.forEach((item) => {
          if (typeof item === "string") {
            sectionContentHtml += `<li>${item}</li>`;
          } else if (typeof item === "object") {
            // Just dump first property as text
            const text = Object.values(item)[0] || "Item";
            sectionContentHtml += `<li>${text}</li>`;
          }
        });
        sectionContentHtml += "</ul>";
      }
      html += createCollapsibleSection(sectionTitle, sectionContentHtml);
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
            margin-top: 15px;
        }
        /* Profile Controls Bar */
        .profile-controls {
            display: flex;
            justify-content: flex-start;
            margin-bottom: 5px;
        }
        .profile-controls a {
            display: inline-flex;
            align-items: center;
        }
        .profile-controls a:hover {
            color: #0d6efd !important;
            text-decoration: underline !important;
        }
        .section {
            padding: 8px;
        }
        .section h2 {
            margin-bottom: 0px;
        }
        h2 {
            font-size: 1.4em;
            margin-bottom: 5px;
            padding-bottom: 4px;
            border-bottom: 1px solid #ddd;
        }
        h3 {
            font-size: 1.2em;
            margin-top: 10px;
            margin-bottom: 10px;
            font-weight: 600;
            color: #2c5282;
            padding-bottom: 3px;
            border-bottom: 1px dotted #cbd5e0;
        }
        .section-content {
            padding: 10px 0 5px 15px;
        }
        ul {
            margin-top: 8px;
            margin-bottom: 15px;
        }
        li {
            margin-bottom: 6px;
            line-height: 1.4;
        }
        /* Styles for Collapsible Header */
        .collapsible-header {
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            border-bottom: 1px solid #ddd;
            margin-bottom: 0;
            transition: background-color 0.2s ease-in-out;
        }
        /* Style the icon container */
        .collapse-icon {
           font-size: 1.1em;
           font-weight: bold;
           color: #495057;
           transition: transform 0.2s ease-in-out; /* Keep transition for potential future use */
        }
        /* Icon visibility rules */
        .collapsible-header .bi-chevron-up {
            display: none; /* Hide UP by default */
        }
        .collapsible-header .bi-chevron-down {
            display: inline-block; /* Show DOWN by default */
        }
        .collapsible-header[aria-expanded="true"] .bi-chevron-up {
            display: inline-block; /* Show UP when expanded */
        }
        .collapsible-header[aria-expanded="true"] .bi-chevron-down {
            display: none; /* Hide DOWN when expanded */
        }
        .collapsible-header:hover {
            background-color: #e9ecef; /* More noticeable hover effect */
        }
        /* Ensure collapsed content doesn't have extra margin */
        .collapse .section-content > *:first-child {
            margin-top: 0;
        }
        .collapse .section-content > *:last-child {
            margin-bottom: 0;
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
