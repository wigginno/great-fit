// Ultra simple profile formatter
function formatProfileData(data) {
  if (!data || typeof data !== "object" || Object.keys(data).length === 0)
    return '<p class="text-gray-500 italic">No profile data available</p>';

  if (
    !(data.skills && data.skills.length > 0) &&
    !(data.sections && data.sections.length > 0) &&
    !Object.entries(data).filter(([key]) => !["id", "email", "owner_email", "contactInformation", "skills", "sections"].includes(key) && data[key] !== null && data[key] !== undefined).length > 0
  ) {
    return '<p class="text-gray-500 italic">No profile data available</p>';
  }

  let html = `
    <div class="space-y-3">
  `;

  const createCollapsibleSection = (title, contentHtml, initiallyExpanded = true) => {
    return `
      <div x-data="{ expanded: ${initiallyExpanded} }" class="border border-gray-200 rounded-md">
        <h2 @click="expanded = !expanded" class="flex justify-between items-center cursor-pointer p-3 bg-gray-50 hover:bg-gray-100 rounded-t-md">
          <span class="font-semibold text-gray-700">${title}</span>
          <svg class="w-5 h-5 text-gray-500 transform transition-transform duration-200" :class="{ 'rotate-180': expanded }" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </h2>
        <div x-show="expanded" x-transition class="p-3 border-t border-gray-200 text-sm text-gray-600">
          ${contentHtml}
        </div>
      </div>
    `;
  };

  if (data.skills && data.skills.length > 0) {
    const skillsHtml = `
      <ul class="flex flex-wrap gap-2 list-none p-0 mt-2">
        ${data.skills.map((skill) => `<li class="bg-indigo-100 text-indigo-700 px-3 py-1 rounded-full text-xs font-medium">${String(skill).trim()}</li>`).join("")}
      </ul>`;
    html += createCollapsibleSection("Skills", skillsHtml, true);
  }

  if (data.sections && data.sections.length > 0) {
    data.sections.forEach((section) => {
      let sectionContentHtml = "";
      if (section.entries && section.entries.length > 0) {
        sectionContentHtml += '<ul class="list-disc pl-5 space-y-1 mt-2">';
        section.entries.forEach((entry) => {
          sectionContentHtml += `<li>${entry}</li>`;
        });
        sectionContentHtml += "</ul>";
      }
      if (section.subsections && section.subsections.length > 0) {
        section.subsections.forEach((subsection) => {
          sectionContentHtml += `<h3 class="font-semibold text-gray-700 mt-3 mb-1 text-base">${subsection.title}</h3>`;
          if (subsection.entries && subsection.entries.length > 0) {
            sectionContentHtml += '<ul class="list-disc pl-5 space-y-1 mt-1">';
            subsection.entries.forEach((entry) => {
              sectionContentHtml += `<li>${entry}</li>`;
            });
            sectionContentHtml += "</ul>";
          }
        });
      }
      html += createCollapsibleSection(section.title, sectionContentHtml, true);
    });
  }

  const ignoredFields = new Set([
    "id", "email", "owner_email", "contactInformation", "skills", "sections",
  ]);
  Object.entries(data)
    .filter(
      ([key, value]) =>
        !ignoredFields.has(key) && value !== null && value !== undefined && String(value).trim() !== "" && (!Array.isArray(value) || value.length > 0)
    )
    .forEach(([key, value]) => {
      const sectionTitle = key
        .replace(/_/g, " ")
        .replace(/([A-Z])/g, " $1") // Add space before uppercase letters for camelCase/PascalCase
        .trim()
        .split(" ")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(" ");

      let sectionContentHtml = "";
      if (typeof value === "string") {
        sectionContentHtml += `<p class="whitespace-pre-wrap mt-2">${value}</p>`;
      } else if (Array.isArray(value) && value.length > 0) {
        sectionContentHtml += '<ul class="list-disc pl-5 space-y-1 mt-2">';
        value.forEach((item) => {
          if (typeof item === "string") {
            sectionContentHtml += `<li>${item}</li>`;
          } else if (typeof item === "object" && item !== null) {
            const itemContent = Object.entries(item)
              .map(([itemKey, itemValue]) => `<strong>${itemKey.replace(/_/g, " ")}:</strong> ${itemValue}`)
              .join('<br>');
            sectionContentHtml += `<li>${itemContent}</li>`;
          }
        });
        sectionContentHtml += "</ul>";
      } else if (typeof value === 'object' && value !== null && Object.keys(value).length > 0) {
        sectionContentHtml += '<div class="space-y-1 mt-2">';
        for (const [objKey, objValue] of Object.entries(value)) {
          const formattedKey = objKey.replace(/_/g, " ").split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
          sectionContentHtml += `<div><strong>${formattedKey}:</strong> ${objValue}</div>`;
        }
        sectionContentHtml += '</div>';
      }

      if (sectionContentHtml.trim() !== "") {
        html += createCollapsibleSection(sectionTitle, sectionContentHtml, false); // Other sections default to collapsed
      }
    });

  html += "</div>";
  return html;
}

// Remove the DOMContentLoaded listener that injects CSS.
// All styling should now be handled by Tailwind classes applied above
// or global styles in your main CSS file if necessary.
// The lightweight collapse toggle is also replaced by Alpine.js x-data, @click, x-show.
