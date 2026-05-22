const ASSET_EDIT_FIELDS = [
  "name",
  "description",
  "description_plain",
  "description_html",
  "same_as",
  "project_identifier",
  "date_published",
  "asset_version",
  "license",
  "asset_type",

  "keyword",
  "alternate_name",
  "application_area",
  "industrial_sector",
  "research_area",
  "scientific_domain",

  "is_part_of",
  "has_part",
  "relevant_to",
  "relevant_resource",

  "contact",
  "creator",
  "citation",

  "relevant_link",
  "platform",
  "platform_resource_identifier",
  "status_info",

  "distribution_json",
  "media_json",
  "note_json",
  "aiod_entry_json",
  "extra_json",
];

function assetEditSetStatus(type, message) {
  const status = document.getElementById("assetEditStatus");
  status.hidden = false;
  status.className = "modal-status " + type;
  status.textContent = message;
}

function assetEditClearStatus() {
  const status = document.getElementById("assetEditStatus");
  status.hidden = true;
  status.textContent = "";
  status.className = "modal-status";
}

function assetEditValues(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }

  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function assetEditSetFieldValue(element, value) {
  if (element.tagName === "SELECT" && element.multiple) {
    const selectedValues = new Set(assetEditValues(value));
    const selectedValuesLower = new Set(
      Array.from(selectedValues).map((item) => item.toLowerCase())
    );

    Array.from(element.options).forEach((option) => {
      option.selected = (
        selectedValues.has(option.value) ||
        selectedValuesLower.has(option.value.toLowerCase())
      );
    });

    if (window.syncEnhancedMultiSelect) {
      window.syncEnhancedMultiSelect(element);
    }

    return;
  }

  element.value = value || "";

  if (window.syncSearchableSelect) {
    window.syncSearchableSelect(element);
  }
}

async function openAssetEditModal(identifier) {
  const modal = document.getElementById("assetEditModal");

  if (!identifier) {
    alert("Missing asset identifier.");
    return;
  }

  modal.hidden = false;
  document.body.classList.add("modal-open");
  assetEditClearStatus();
  assetEditSetStatus("loading", "Loading asset metadata...");

  try {
    const response = await fetch(`/asset-edit-data?identifier=${encodeURIComponent(identifier)}`);
    const data = await response.json();

    if (!response.ok || !data.ok) {
      const message = data.error?.message || "Unable to load asset metadata.";
      throw new Error(message);
    }

    document.getElementById("edit_identifier").value = data.identifier || identifier;

    const form = data.form || {};

    ASSET_EDIT_FIELDS.forEach((fieldName) => {
      const element = document.getElementById("edit_" + fieldName);
      if (!element) return;
      assetEditSetFieldValue(element, form[fieldName] || "");
    });

    const freeCheckbox = document.getElementById("edit_is_accessible_for_free");
    freeCheckbox.checked = form.is_accessible_for_free === "on";

    const distributionSection = document.querySelector("#assetEditModal [data-resource-prefix='distribution']");
    if (window.renderResourceItems && distributionSection) {
      window.renderResourceItems(distributionSection, form.distribution_items || []);
    }

    const mediaSection = document.querySelector("#assetEditModal [data-resource-prefix='media']");
    if (window.renderResourceItems && mediaSection) {
      window.renderResourceItems(mediaSection, form.media_items || []);
    }

    const noteSection = document.querySelector("#assetEditModal [data-note-section]");
    if (window.renderNoteItems && noteSection) {
      window.renderNoteItems(noteSection, form.note_items || []);
    }

    assetEditClearStatus();
  } catch (error) {
    assetEditSetStatus("error", error.message || String(error));
  }
}

function closeAssetEditModal() {
  const modal = document.getElementById("assetEditModal");
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  assetEditClearStatus();
}

document.addEventListener("keydown", function(event) {
  if (event.key === "Escape") {
    const modal = document.getElementById("assetEditModal");
    if (modal && !modal.hidden) {
      closeAssetEditModal();
    }
  }
});

document.addEventListener("DOMContentLoaded", function() {
  const modal = document.getElementById("assetEditModal");
  const form = document.getElementById("assetEditForm");

  if (!modal || !form) return;

  modal.addEventListener("click", function(event) {
    if (event.target === modal) {
      closeAssetEditModal();
    }
  });

  form.addEventListener("submit", async function(event) {
    event.preventDefault();

    if (!confirm("Update this asset metadata on AIoD?")) {
      return;
    }

    assetEditSetStatus("loading", "Updating asset metadata...");

    try {
      const formData = new FormData(form);

      const response = await fetch("/asset-update", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        const message = data.error?.message || "Asset update failed.";
        throw new Error(message);
      }

      assetEditSetStatus("success", data.message || "Asset updated successfully.");

      setTimeout(() => {
        window.location.reload();
      }, 900);
    } catch (error) {
      assetEditSetStatus("error", error.message || String(error));
    }
  });
});
