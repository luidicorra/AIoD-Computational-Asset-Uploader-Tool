(function () {
  let activePopover = null;

  function closePopover() {
    if (activePopover) {
      activePopover.remove();
      activePopover = null;
    }
  }

  function openPopover(button) {
    closePopover();

    const message = button.dataset.fieldHelp;
    if (!message) return;

    const popover = document.createElement("div");
    popover.className = "field-info-popover";
    popover.textContent = message;
    document.body.appendChild(popover);

    const rect = button.getBoundingClientRect();
    const top = rect.bottom + window.scrollY + 8;
    const left = Math.min(
      rect.left + window.scrollX,
      window.scrollX + document.documentElement.clientWidth - 340
    );

    popover.style.top = top + "px";
    popover.style.left = Math.max(12, left) + "px";
    activePopover = popover;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-field-help]");
    if (button) {
      event.stopPropagation();
      openPopover(button);
      return;
    }

    if (!event.target.closest(".field-info-popover")) {
      closePopover();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePopover();
    }
  });
})();
