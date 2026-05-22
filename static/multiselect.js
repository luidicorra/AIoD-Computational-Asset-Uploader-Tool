(function () {
  function getSelectOptions(select) {
    return Array.from(select.options).filter((option) => !option.disabled);
  }

  function selectedOptions(select) {
    return getSelectOptions(select).filter((option) => option.selected);
  }

  function syncEnhancedMultiSelect(select) {
    const root = select.enhancedMultiSelectRoot;
    if (!root) return;

    const selectedValues = new Set(selectedOptions(select).map((option) => option.value));
    const optionButtons = root.querySelectorAll("[data-multiselect-option]");
    const chips = root.querySelector("[data-multiselect-chips]");

    optionButtons.forEach((button) => {
      const isSelected = selectedValues.has(button.dataset.value);
      button.classList.toggle("selected", isSelected);
      button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    });

    chips.innerHTML = "";

    const selected = selectedOptions(select).sort((left, right) => (
      left.textContent.trim().localeCompare(right.textContent.trim(), undefined, { sensitivity: "base" })
    ));
    if (!selected.length) {
      const empty = document.createElement("span");
      empty.className = "multi-chip-empty";
      empty.textContent = "No values selected";
      chips.appendChild(empty);
      return;
    }

    selected.forEach((option) => {
      const chip = document.createElement("span");
      chip.className = "multi-chip";

      const label = document.createElement("span");
      label.textContent = option.textContent.trim();

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "multi-chip-remove";
      remove.setAttribute("aria-label", "Remove " + option.textContent.trim());
      remove.textContent = "x";
      remove.addEventListener("click", () => {
        option.selected = false;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncEnhancedMultiSelect(select);
      });

      chip.appendChild(label);
      chip.appendChild(remove);
      chips.appendChild(chip);
    });
  }

  function filterEnhancedMultiSelect(root) {
    const search = root.querySelector("[data-multiselect-search]");
    const empty = root.querySelector("[data-multiselect-no-results]");
    const query = (search?.value || "").trim().toLowerCase();
    let visibleCount = 0;

    root.querySelectorAll("[data-multiselect-option]").forEach((button) => {
      const matches = button.textContent.toLowerCase().includes(query);
      button.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    if (empty) {
      empty.hidden = visibleCount > 0;
    }
  }

  function enhanceMultiSelect(select) {
    if (select.enhancedMultiSelectRoot || !select.multiple) return;

    select.classList.add("multi-select-native");

    const root = document.createElement("div");
    root.className = "enhanced-multiselect";

    const search = document.createElement("input");
    search.type = "search";
    search.className = "multi-search";
    search.placeholder = "Search values";
    search.dataset.multiselectSearch = "";
    search.setAttribute("aria-label", "Search values");
    search.addEventListener("input", () => filterEnhancedMultiSelect(root));

    const list = document.createElement("div");
    list.className = "multi-option-list";
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", select.getAttribute("aria-label") || select.name || "Options");

    getSelectOptions(select).forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "multi-option";
      button.dataset.multiselectOption = "";
      button.dataset.value = option.value;
      button.textContent = option.textContent.trim();
      button.setAttribute("aria-pressed", option.selected ? "true" : "false");

      button.addEventListener("click", () => {
        option.selected = !option.selected;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncEnhancedMultiSelect(select);
      });

      list.appendChild(button);
    });

    const noResults = document.createElement("div");
    noResults.className = "multi-no-results";
    noResults.dataset.multiselectNoResults = "";
    noResults.hidden = true;
    noResults.textContent = "No matching values";
    list.appendChild(noResults);

    const chips = document.createElement("div");
    chips.className = "multi-chip-list";
    chips.dataset.multiselectChips = "";

    root.appendChild(search);
    root.appendChild(list);
    root.appendChild(chips);
    select.insertAdjacentElement("afterend", root);

    select.enhancedMultiSelectRoot = root;
    syncEnhancedMultiSelect(select);
  }

  window.syncEnhancedMultiSelect = syncEnhancedMultiSelect;

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("select.multi-select[multiple]").forEach(enhanceMultiSelect);
  });
})();
