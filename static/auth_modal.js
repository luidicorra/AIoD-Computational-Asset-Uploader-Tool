(function () {
  const modal = document.getElementById("authModal");
  const body = document.getElementById("authModalBody");
  const closeButton = document.querySelector("[data-auth-modal-close]");
  let refreshTimer = null;

  if (!modal || !body) return;

  function stopRefresh() {
    if (refreshTimer) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function bindForms() {
    body.querySelectorAll("[data-auth-modal-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submitter = event.submitter;
        const formData = new FormData(form);

        if (submitter && submitter.name) {
          formData.set(submitter.name, submitter.value);
        }

        if (submitter?.value === "start_auth") {
          showAuthFlowLoading(form);
        }

        await loadAuthPanel({
          method: "POST",
          body: formData,
        });
      });
    });
  }

  function showAuthFlowLoading(form) {
    form.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });

    const flowCard = body.querySelector(".auth-flow-card");
    if (!flowCard) return;

    flowCard.dataset.authRunning = "true";
    flowCard.innerHTML = `
      <div class="auth-panel-heading">
        <div>
          <h2>Authentication flow</h2>
        </div>
        <span class="status-pill running">Starting</span>
      </div>

      <div class="auth-flow-loading" role="status" aria-live="polite">
        <span class="auth-spinner" aria-hidden="true"></span>
        <strong>Starting authentication flow...</strong>
        <p>Preparing the AIoD login link. This usually takes a few seconds.</p>
      </div>
    `;
  }

  function scheduleRefresh() {
    stopRefresh();

    const outputCard = body.querySelector("[data-auth-running='true']");
    if (!outputCard || modal.hidden) return;

    refreshTimer = window.setTimeout(() => {
      loadAuthPanel();
    }, 3000);
  }

  async function loadAuthPanel(options) {
    if (!body.innerHTML.trim()) {
      body.innerHTML = '<div class="modal-loading">Loading authentication status...</div>';
    }

    try {
      const response = await fetch("/auth/modal", {
        method: "GET",
        credentials: "same-origin",
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      body.innerHTML = await response.text();
      bindForms();
      scheduleRefresh();
    } catch (error) {
      body.innerHTML = `
        <div class="warn">
          <strong>Unable to load authentication status.</strong>
          <p>${error.message}</p>
          <p><a class="button-link" href="/auth">Open Auth check page</a></p>
        </div>
      `;
    }
  }

  function openAuthModal(event) {
    if (event) event.preventDefault();
    modal.hidden = false;
    document.body.classList.add("modal-open");
    loadAuthPanel();
  }

  function closeAuthModal() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    stopRefresh();
  }

  document.querySelectorAll("[data-auth-modal-open]").forEach((trigger) => {
    trigger.addEventListener("click", openAuthModal);
  });

  if (closeButton) {
    closeButton.addEventListener("click", closeAuthModal);
  }

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeAuthModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      closeAuthModal();
    }
  });

  window.openAuthModal = openAuthModal;
  window.closeAuthModal = closeAuthModal;
})();
