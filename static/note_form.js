(function () {
  function createNoteItem(values, index) {
    const item = document.createElement("div");
    item.className = "media-item note-item";

    const header = document.createElement("div");
    header.className = "media-item-header";

    const title = document.createElement("h4");
    title.textContent = "Note " + (index + 1);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost media-remove-button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      item.remove();
      renumberNoteItems(item.closest("[data-note-section]"));
    });

    header.appendChild(title);
    header.appendChild(remove);
    item.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "form-grid media-item-grid";

    const field = document.createElement("div");
    field.className = "field full";

    const labelRow = document.createElement("div");
    labelRow.className = "field-label-row";

    const label = document.createElement("label");
    label.textContent = "Value";

    const info = document.createElement("button");
    info.type = "button";
    info.className = "vocabulary-info-button field-info-button";
    info.textContent = "i";
    info.setAttribute("aria-label", "Show information about note value");
    info.dataset.fieldHelp = "The string value for extra textual information about this AI resource.";

    labelRow.appendChild(label);
    labelRow.appendChild(info);

    const textarea = document.createElement("textarea");
    textarea.name = "note_value";
    textarea.rows = 4;
    textarea.maxLength = 8000;
    textarea.placeholder = "A brief record of points or ideas about this AI resource.";
    textarea.value = values.value || "";

    field.appendChild(labelRow);
    field.appendChild(textarea);
    grid.appendChild(field);
    item.appendChild(grid);

    return item;
  }

  function renumberNoteItems(section) {
    if (!section) return;

    section.querySelectorAll(".note-item h4").forEach((title, index) => {
      title.textContent = "Note " + (index + 1);
    });
  }

  function renderNoteItems(section, items) {
    if (!section) return;

    const list = section.querySelector("[data-note-list]");
    if (!list) return;

    list.innerHTML = "";

    const normalizedItems = Array.isArray(items) && items.length ? items : [{}];
    normalizedItems.forEach((item, index) => {
      list.appendChild(createNoteItem(item || {}, index));
    });
  }

  function initNoteSection(section) {
    if (section.noteInitialized) return;

    section.noteInitialized = true;
    renderNoteItems(section, [{}]);

    const addButton = section.querySelector("[data-note-add]");
    addButton?.addEventListener("click", () => {
      const list = section.querySelector("[data-note-list]");
      const index = list.querySelectorAll(".note-item").length;
      list.appendChild(createNoteItem({}, index));
    });
  }

  window.renderNoteItems = renderNoteItems;

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-note-section]").forEach(initNoteSection);
  });
})();
