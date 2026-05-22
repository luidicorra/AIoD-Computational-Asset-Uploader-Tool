(function () {
  const RESOURCE_CONFIG = {
    media: {
      title: "Media item",
      addLabel: "Add media item",
      includeBinaryBlob: true,
    },
    distribution: {
      title: "Distribution item",
      addLabel: "Add distribution item",
      includeBinaryBlob: false,
    },
  };

  const RESOURCE_FIELDS = [
    {
      name: "name",
      label: "Name",
      maxLength: 256,
      placeholder: "Name of this file.",
    },
    {
      name: "content_url",
      label: "Content URL",
      maxLength: 1800,
      type: "url",
      placeholder: "https://www.example.com/dataset/file.csv",
      help: "The URL where this resource can be accessed.",
    },
    {
      name: "description",
      label: "Description",
      maxLength: 1800,
      textarea: true,
      placeholder: "Description of this file.",
      help: "A short description of this file.",
    },
    {
      name: "encoding_format",
      label: "Encoding format",
      maxLength: 256,
      placeholder: "text/csv",
      help: "The MIME type or file format of this file.",
    },
    {
      name: "content_size_kb",
      label: "Content size KB",
      type: "number",
      min: 0,
      placeholder: "10000",
    },
    {
      name: "date_published",
      label: "Date published",
      type: "datetime-local",
      help: "The datetime UTC on which this resource was first published on an external platform.",
    },
    {
      name: "checksum",
      label: "Checksum",
      maxLength: 1800,
      placeholder: "e3b0c44298fc1c149afbf4c8996fb924...",
      help: "The checksum value used to verify the content.",
    },
    {
      name: "checksum_algorithm",
      label: "Checksum algorithm",
      maxLength: 64,
      placeholder: "sha256",
      help: "The algorithm used to calculate the checksum.",
    },
    {
      name: "copyright",
      label: "Copyright",
      maxLength: 256,
      placeholder: "2010-2020 Example Company. All rights reserved.",
      help: "Copyright or rights statement for this resource.",
    },
    {
      name: "technology_readiness_level",
      label: "Technology readiness level",
      type: "number",
      min: 1,
      max: 9,
      placeholder: "1",
      help: "The technology readiness level (TRL) of this resource. TRL 1 is the lowest and stands for 'Basic principles observed'; TRL 9 is the highest and stands for 'actual system proven in operational environment'.",
    },
  ];

  const HIDDEN_RESOURCE_FIELDS = [
    "platform",
    "platform_resource_identifier",
  ];

  function inputName(prefix, fieldName) {
    return prefix + "_" + fieldName;
  }

  function createResourceField(prefix, field, values) {
    const wrapper = document.createElement("div");
    wrapper.className = field.textarea ? "field full" : "field";

    const label = document.createElement("label");
    label.textContent = field.label;

    if (field.help) {
      const labelRow = document.createElement("div");
      labelRow.className = "field-label-row";

      const info = document.createElement("button");
      info.type = "button";
      info.className = "vocabulary-info-button field-info-button";
      info.textContent = "i";
      info.setAttribute("aria-label", "Show information about " + field.label);
      info.dataset.fieldHelp = field.help;

      labelRow.appendChild(label);
      labelRow.appendChild(info);
      wrapper.appendChild(labelRow);
    } else {
      wrapper.appendChild(label);
    }

    const control = field.textarea ? document.createElement("textarea") : document.createElement("input");
    control.name = inputName(prefix, field.name);
    control.value = values[field.name] || "";

    if (field.textarea) {
      control.rows = 4;
    } else {
      control.type = field.type || "text";
    }

    if (field.maxLength) {
      control.maxLength = field.maxLength;
    }

    if (field.min !== undefined) {
      control.min = field.min;
    }

    if (field.max !== undefined) {
      control.max = field.max;
    }

    if (field.placeholder) {
      control.placeholder = field.placeholder;
    }

    wrapper.appendChild(control);
    return wrapper;
  }

  function createHiddenResourceField(prefix, fieldName, values) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = inputName(prefix, fieldName);
    input.value = values[fieldName] || "";
    return input;
  }

  function createResourceItem(prefix, values, index) {
    const config = RESOURCE_CONFIG[prefix] || RESOURCE_CONFIG.media;
    const item = document.createElement("div");
    item.className = "media-item";

    const header = document.createElement("div");
    header.className = "media-item-header";

    const title = document.createElement("h4");
    title.textContent = config.title + " " + (index + 1);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost media-remove-button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      item.remove();
      renumberResourceItems(item.closest("[data-resource-section]"));
    });

    header.appendChild(title);
    header.appendChild(remove);
    item.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "form-grid media-item-grid";

    RESOURCE_FIELDS.forEach((field) => {
      grid.appendChild(createResourceField(prefix, field, values));
    });

    HIDDEN_RESOURCE_FIELDS.forEach((fieldName) => {
      grid.appendChild(createHiddenResourceField(prefix, fieldName, values));
    });

    if (config.includeBinaryBlob) {
      grid.appendChild(createHiddenResourceField(prefix, "binary_blob", values));
    }

    item.appendChild(grid);
    return item;
  }

  function renumberResourceItems(section) {
    if (!section) return;

    const prefix = section.dataset.resourcePrefix || "media";
    const config = RESOURCE_CONFIG[prefix] || RESOURCE_CONFIG.media;

    section.querySelectorAll(".media-item h4").forEach((title, index) => {
      title.textContent = config.title + " " + (index + 1);
    });
  }

  function renderResourceItems(section, items) {
    if (!section) return;

    const list = section.querySelector("[data-resource-list]");
    if (!list) return;

    const prefix = section.dataset.resourcePrefix || "media";
    list.innerHTML = "";

    const normalizedItems = Array.isArray(items) && items.length ? items : [{}];
    normalizedItems.forEach((item, index) => {
      list.appendChild(createResourceItem(prefix, item || {}, index));
    });
  }

  function initResourceSection(section) {
    if (section.resourceInitialized) return;

    section.resourceInitialized = true;
    renderResourceItems(section, [{}]);

    const addButton = section.querySelector("[data-resource-add]");
    addButton?.addEventListener("click", () => {
      const list = section.querySelector("[data-resource-list]");
      const prefix = section.dataset.resourcePrefix || "media";
      const index = list.querySelectorAll(".media-item").length;
      list.appendChild(createResourceItem(prefix, {}, index));
    });
  }

  window.renderResourceItems = renderResourceItems;
  window.renderMediaItems = renderResourceItems;

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-resource-section]").forEach(initResourceSection);
  });
})();
