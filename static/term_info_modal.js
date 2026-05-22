(function () {
  const VOCABULARIES = {
    researchArea: {
      scriptId: "researchAreaTermsData",
      title: "Research Areas",
      emptyMessage: "Research area terms could not be loaded.",
    },
    industrialSector: {
      scriptId: "industrialSectorTermsData",
      title: "Industrial Sectors",
      emptyMessage: "Industrial sector terms could not be loaded.",
    },
    scientificDomain: {
      scriptId: "scientificDomainTermsData",
      title: "Scientific Domains",
      emptyMessage: "Scientific domain terms could not be loaded.",
    },
  };

  function readTerms(scriptId) {
    const script = document.getElementById(scriptId);
    if (!script) return [];

    try {
      const terms = JSON.parse(script.textContent || "[]");
      return Array.isArray(terms) ? terms : [];
    } catch (error) {
      return [];
    }
  }

  function renderSubterms(subterms) {
    const visibleSubterms = Array.isArray(subterms) ? subterms.filter((item) => item.term) : [];
    if (!visibleSubterms.length) return null;

    const list = document.createElement("ul");
    list.className = "vocabulary-subterm-list";

    visibleSubterms.forEach((subterm) => {
      const item = document.createElement("li");

      const term = document.createElement("strong");
      term.textContent = subterm.term;
      item.appendChild(term);

      if (subterm.definition) {
        const definition = document.createElement("p");
        definition.textContent = subterm.definition;
        item.appendChild(definition);
      }

      const nested = renderSubterms(subterm.subterms);
      if (nested) {
        item.appendChild(nested);
      }

      list.appendChild(item);
    });

    return list;
  }

  function renderTermDetail(container, term) {
    container.innerHTML = "";

    if (!term) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Select a term to view details.";
      container.appendChild(empty);
      return;
    }

    const title = document.createElement("h3");
    title.textContent = term.term;
    container.appendChild(title);

    if (term.definition) {
      const definition = document.createElement("p");
      definition.className = "vocabulary-definition";
      definition.textContent = term.definition;
      container.appendChild(definition);
    }

    const subterms = renderSubterms(term.subterms);
    if (subterms) {
      const heading = document.createElement("h4");
      heading.textContent = "Subterms";
      container.appendChild(heading);
      container.appendChild(subterms);
    }
  }

  function openVocabularyModal(vocabularyKey) {
    const config = VOCABULARIES[vocabularyKey];
    if (!config) return;

    const modal = document.getElementById("vocabularyInfoModal");
    const title = modal?.querySelector("[data-vocabulary-title]");
    const list = modal?.querySelector("[data-vocabulary-list]");
    const detail = modal?.querySelector("[data-vocabulary-detail]");
    const terms = readTerms(config.scriptId);

    if (!modal || !title || !list || !detail) return;

    title.textContent = config.title;
    list.innerHTML = "";

    if (!terms.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = config.emptyMessage;
      list.appendChild(empty);
      renderTermDetail(detail, null);
    } else {
      terms.forEach((term, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "vocabulary-term-button";
        button.textContent = term.term;

        button.addEventListener("click", () => {
          list.querySelectorAll(".vocabulary-term-button").forEach((item) => {
            item.classList.toggle("active", item === button);
          });
          renderTermDetail(detail, term);
        });

        list.appendChild(button);

        if (index === 0) {
          button.classList.add("active");
          renderTermDetail(detail, term);
        }
      });
    }

    modal.hidden = false;
    document.body.classList.add("modal-open");
  }

  function closeVocabularyModal() {
    const modal = document.getElementById("vocabularyInfoModal");
    if (!modal) return;

    modal.hidden = true;
    document.body.classList.remove("modal-open");
  }

  document.addEventListener("click", (event) => {
    const infoButton = event.target.closest("[data-vocabulary-info]");
    if (infoButton) {
      openVocabularyModal(infoButton.dataset.vocabularyInfo);
      return;
    }

    if (event.target.closest("[data-vocabulary-close]")) {
      closeVocabularyModal();
      return;
    }

    const modal = document.getElementById("vocabularyInfoModal");
    if (event.target === modal) {
      closeVocabularyModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeVocabularyModal();
    }
  });
})();
