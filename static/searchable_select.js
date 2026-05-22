(function () {
  function syncSearchableSelect(select) {
    const root = select.searchableSelectRoot;
    if (!root) return;

    const valueLabel = root.querySelector("[data-searchable-select-value]");
    const selected = select.selectedOptions[0];
    valueLabel.textContent = selected && selected.value
      ? selected.textContent.trim()
      : (select.dataset.emptyLabel || "No value selected");
  }

  function filterOptions(root) {
    const query = (root.querySelector("[data-searchable-select-search]")?.value || "").trim().toLowerCase();
    const empty = root.querySelector("[data-searchable-select-no-results]");
    let visibleCount = 0;

    root.querySelectorAll("[data-searchable-select-option]").forEach((button) => {
      const matches = button.textContent.toLowerCase().includes(query);
      button.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    if (empty) {
      empty.hidden = visibleCount > 0;
    }
  }

  function enhanceSearchableSelect(select) {
    if (select.searchableSelectRoot) return;

    select.classList.add("searchable-select-native");

    const root = document.createElement("div");
    root.className = "enhanced-searchable-select";

    const search = document.createElement("input");
    search.type = "search";
    search.className = "single-select-search";
    search.placeholder = select.dataset.searchPlaceholder || "Search values";
    search.dataset.searchableSelectSearch = "";
    search.setAttribute("aria-label", select.dataset.searchLabel || search.placeholder);
    search.addEventListener("input", () => filterOptions(root));

    const list = document.createElement("div");
    list.className = "single-option-list";
    list.setAttribute("role", "listbox");

    Array.from(select.options)
      .filter((option) => option.value && !option.disabled)
      .forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "single-option";
        button.dataset.searchableSelectOption = "";
        button.dataset.value = option.value;
        button.textContent = option.textContent.trim();

        button.addEventListener("click", () => {
          select.value = option.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
          syncSearchableSelect(select);
        });

        list.appendChild(button);
      });

    const noResults = document.createElement("div");
    noResults.className = "multi-no-results";
    noResults.dataset.searchableSelectNoResults = "";
    noResults.hidden = true;
    noResults.textContent = "No matching values";
    list.appendChild(noResults);

    const selectedValue = document.createElement("div");
    selectedValue.className = "single-selected-value";
    selectedValue.dataset.searchableSelectValue = "";

    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "single-select-clear";
    clear.textContent = "Clear selection";
    clear.addEventListener("click", () => {
      select.value = "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      syncSearchableSelect(select);
    });

    root.appendChild(search);
    root.appendChild(list);
    root.appendChild(selectedValue);
    root.appendChild(clear);
    select.insertAdjacentElement("afterend", root);

    select.searchableSelectRoot = root;
    syncSearchableSelect(select);
  }

  window.syncSearchableSelect = syncSearchableSelect;

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("select.searchable-select").forEach(enhanceSearchableSelect);
  });
})();
