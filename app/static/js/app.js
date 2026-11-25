(() => {
  const root = document.getElementById("hireboard");
  if (!root) return;

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  let account = null;
  let jobs = [];

  const statusNames = {
    submitted: "Submitted",
    applied: "Applied",
    reviewed: "Reviewed",
    shortlisted: "Shortlisted",
    interview: "Interview",
    offered: "Offered",
    hired: "Hired",
    rejected: "Rejected",
    withdrawn: "Withdrawn"
  };

  const actionsByState = {
    submitted: ["review"],
    reviewed: ["shortlist"],
    shortlisted: ["reject", "hire"]
  };

  const actionNames = {
    review: "Mark reviewed",
    shortlist: "Shortlist",
    reject: "Reject",
    hire: "Mark hired"
  };

  function element(tag, className = "", text = "") {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== "") result.textContent = String(text);
    return result;
  }

  function message(text, error = false) {
    const feedback = $("#hb-feedback");
    feedback.textContent = text;
    feedback.hidden = false;
    feedback.classList.toggle("is-error", error);
    feedback.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function empty(container, text) {
    container.replaceChildren(element("div", "hb-empty", text));
  }

  function button(text, handler, variant = "") {
    const result = element("button", `hb-button ${variant}`.trim(), text);
    result.type = "button";
    result.addEventListener("click", handler);
    return result;
  }

  function badge(text) {
    return element("span", "hb-badge", text);
  }

  function paragraph(text, className = "") {
    return element("p", className, text || "");
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {})
      }
    });

    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
      if (response.status === 401) {
        throw new Error("Your session has expired. Please sign in again.");
      }
      throw new Error(`Unexpected server response (${response.status}).`);
    }

    const data = await response.json();

    if (!response.ok || data.ok === false) {
      const detail = data.detail || data.error || "The request failed";
      throw new Error(
        typeof detail === "string" ? detail : "Please check the information entered."
      );
    }

    return data;
  }

  function showPage(page) {
    const target = $(`[data-section="${page}"]`);

    if (!target || target.hidden) return;

    $$(".hb-page").forEach((section) => {
      section.classList.toggle("is-active", section === target);
    });

    $$(".hb-tab").forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.page === page);
    });

    if (page === "jobs") loadJobs();
    if (page === "applications") loadApplications();
    if (page === "notifications") loadNotifications();
    if (page === "employer") loadEmployerListings();
    if (page === "admin") loadPending();
  }

  function createJobCard(job) {
    const card = element("article", "hb-card");

    card.append(
      badge(job.apply_mode === "external" ? "External application" : "Apply on HireBoard"),
      element("h3", "", job.title),
      paragraph(job.company, "hb-company"),
      paragraph(job.description, "hb-description"),
      paragraph(`Deadline: ${job.deadline}`, "hb-meta")
    );

    const actions = element("div", "hb-card-actions");

    if (job.apply_mode === "external") {
      if (job.external_url) {
        try {
          const url = new URL(job.external_url);
          if (["http:", "https:"].includes(url.protocol)) {
            const link = element("a", "hb-button", "Apply on external website");
            link.href = url.href;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            actions.append(link);
          }
        } catch {}
      }
    } else {
      actions.append(
        button("Apply now", () => openApplication(job))
      );
    }

    card.append(actions);
    return card;
  }

  function renderJobs() {
    const container = $("#hb-jobs");
    const term = $("#hb-search-input").value.trim().toLowerCase();

    const filtered = jobs.filter((job) => {
      const content = `${job.title} ${job.company} ${job.description}`;
      return content.toLowerCase().includes(term);
    });

    if (!filtered.length) {
      empty(container, "No matching published jobs were found.");
      return;
    }

    container.replaceChildren();

    filtered.forEach((job) => {
      container.append(createJobCard(job));
    });
  }

  async function loadJobs() {
    const container = $("#hb-jobs");

    try {
      const data = await api("/api/ui/jobs");
      jobs = data.jobs || [];
      $("#hb-job-count").textContent = jobs.length;
      renderJobs();
    } catch (error) {
      empty(container, error.message);
    }
  }

  function openApplication(job) {
    const form = $("#hb-application-form");
    form.reset();
    form.elements.listing_id.value = job.id;
    $("#hb-apply-title").textContent = `Apply: ${job.title}`;
    $("#hb-apply-dialog").showModal();
  }

  async function submitApplication(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;

    try {
      const payload = {
        listing_id: Number(form.elements.listing_id.value),
        cover_letter: form.elements.cover_letter.value.trim(),
        resume_text: form.elements.resume_text.value.trim()
      };

      await api("/api/graduates/applications", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      $("#hb-apply-dialog").close();
      message("Application submitted successfully.");
      showPage("applications");
    } catch (error) {
      message(error.message, true);
    } finally {
      submit.disabled = false;
    }
  }

  async function loadApplications() {
    const container = $("#hb-applications");

    try {
      const data = await api("/api/graduates/applications");
      const applications = data.applications || [];

      $("#hb-secondary-count").textContent = applications.length;

      if (!applications.length) {
        empty(container, "You have not submitted any applications yet.");
        return;
      }

      container.replaceChildren();

      applications.forEach((application) => {
        const card = element("article", "hb-card");
        const state = application.state || "unknown";

        card.append(
          badge(statusNames[state] || state),
          element(
            "h3",
            "",
            application.listing_title || `Listing #${application.listing_id}`
          ),
          paragraph(application.listing_company, "hb-company"),
          paragraph(`Application #${application.id}`, "hb-meta"),
          paragraph(`Current status: ${statusNames[state] || state}`)
        );

        container.append(card);
      });
    } catch (error) {
      empty(container, error.message);
    }
  }

  async function subscribe() {
    try {
      const data = await api("/api/ui/subscribe", {
        method: "POST"
      });

      message(
        data.already_subscribed
          ? "You are already subscribed to job notifications."
          : "You are now subscribed to job notifications."
      );
    } catch (error) {
      message(error.message, true);
    }
  }

  async function loadNotifications() {
    const container = $("#hb-notifications");

    try {
      const data = await api("/api/ui/notifications");
      const notifications = data.notifications || [];

      if (!notifications.length) {
        empty(container, "You have no notifications yet.");
        return;
      }

      container.replaceChildren();

      notifications.forEach((notification) => {
        const card = element("article", "hb-card");

        card.append(
          badge("Job alert"),
          paragraph(notification.message, "hb-description")
        );

        container.append(card);
      });
    } catch (error) {
      empty(container, error.message);
    }
  }

  function employerListingCard(listing) {
    const card = element("article", "hb-card");

    card.append(
      badge(listing.status),
      element("h3", "", listing.title),
      paragraph(listing.company, "hb-company"),
      paragraph(listing.description, "hb-description"),
      paragraph(`Deadline: ${listing.deadline}`, "hb-meta")
    );

    const actions = element("div", "hb-card-actions");

    actions.append(
      button(
        "View applicants",
        () => loadApplicants(listing),
        "hb-button-outline"
      )
    );

    card.append(actions);
    return card;
  }

  async function loadEmployerListings() {
    const container = $("#hb-employer-listings");

    try {
      const data = await api("/api/ui/employer/listings");
      const listings = data.listings || [];

      $("#hb-secondary-count").textContent = listings.length;

      if (!listings.length) {
        empty(container, "You have not created any job listings yet.");
        return;
      }

      container.replaceChildren();

      listings.forEach((listing) => {
        container.append(employerListingCard(listing));
      });
    } catch (error) {
      empty(container, error.message);
    }
  }

  async function loadApplicants(listing) {
    const panel = $("#hb-applicant-panel");
    const container = $("#hb-applicant-list");

    panel.hidden = false;
    $("#hb-applicant-title").textContent = `Applicants: ${listing.title}`;

    empty(container, "Loading applicants...");

    try {
      const data = await api(`/api/listings/${listing.id}/applicants`);
      const applicants = data.applicants || [];

      if (!applicants.length) {
        empty(container, "No applications have been received for this listing.");
        return;
      }

      container.replaceChildren();

      applicants.forEach((application) => {
        const card = element("article", "hb-applicant");

        card.append(
          element(
            "h4",
            "",
            `Application #${application.id} · Graduate #${application.graduate_id}`
          ),
          badge(statusNames[application.state] || application.state)
        );

        const cover = element("details");
        cover.append(
          element("summary", "", "View cover letter"),
          paragraph(application.cover_letter, "hb-description")
        );

        const resume = element("details");
        resume.append(
          element("summary", "", "View resume"),
          paragraph(application.resume_text, "hb-description")
        );

        const actions = element("div", "hb-card-actions");

        (actionsByState[application.state] || []).forEach((action) => {
          actions.append(
            button(
              actionNames[action],
              async () => {
                const confirmed = confirm(
                  `Confirm ${action} for application #${application.id}?`
                );

                if (!confirmed) return;

                try {
                  await api(
                    `/api/applications/${application.id}/transition`,
                    {
                      method: "POST",
                      body: JSON.stringify({ action })
                    }
                  );

                  message("Application status updated.");
                  await loadApplicants(listing);
                } catch (error) {
                  message(error.message, true);
                }
              },
              action === "reject" ? "hb-button-danger" : ""
            )
          );
        });

        card.append(cover, resume, actions);
        container.append(card);
      });

      panel.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    } catch (error) {
      empty(container, error.message);
    }
  }

  async function submitListing(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;

    try {
      const payload = {
        title: form.elements.title.value.trim(),
        company: form.elements.company.value.trim(),
        description: form.elements.description.value.trim(),
        apply_mode: form.elements.apply_mode.value,
        deadline: form.elements.deadline.value,
        external_url: form.elements.external_url.value.trim() || null
      };

      await api("/api/ui/employer/listings", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      form.reset();
      $("#hb-external-field").hidden = true;
      $("#hb-external-field input").required = false;

      message("Job listing submitted for administrator approval.");
      await loadEmployerListings();
    } catch (error) {
      message(error.message, true);
    } finally {
      submit.disabled = false;
    }
  }

  function pendingCard(listing) {
    const card = element("article", "hb-card");

    card.append(
      badge("Pending approval"),
      element("h3", "", listing.title),
      paragraph(listing.company, "hb-company"),
      paragraph(listing.description, "hb-description"),
      paragraph(`Deadline: ${listing.deadline}`, "hb-meta"),
      paragraph(`Application mode: ${listing.apply_mode}`, "hb-meta")
    );

    const actions = element("div", "hb-card-actions");

    for (const decision of ["publish", "reject"]) {
      const label = decision === "publish"
        ? "Publish listing"
        : "Reject listing";

      actions.append(
        button(
          label,
          async () => {
            if (!confirm(`${label}: ${listing.title}?`)) return;

            try {
              await api(
                `/api/ui/admin/listings/${listing.id}/${decision}`,
                { method: "POST" }
              );

              message(
                decision === "publish"
                  ? "Listing published and subscribers notified."
                  : "Listing rejected."
              );

              await loadPending();
            } catch (error) {
              message(error.message, true);
            }
          },
          decision === "reject" ? "hb-button-danger" : ""
        )
      );
    }

    card.append(actions);
    return card;
  }

  async function loadPending() {
    const container = $("#hb-pending");

    try {
      const data = await api("/api/ui/admin/pending");
      const listings = data.listings || [];

      $("#hb-secondary-count").textContent = listings.length;

      if (!listings.length) {
        empty(container, "There are no listings awaiting approval.");
        return;
      }

      container.replaceChildren();

      listings.forEach((listing) => {
        container.append(pendingCard(listing));
      });
    } catch (error) {
      empty(container, error.message);
    }
  }

  async function exportApplicants(listingId) {
    const data = await api(`/api/admin/listings/${listingId}/export`);

    const blob = new Blob(
      [JSON.stringify(data.package || [], null, 2)],
      { type: "application/json" }
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `applicants-listing-${listingId}.json`;
    document.body.append(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function submitExport(event) {
    event.preventDefault();

    const id = Number(event.currentTarget.elements.listing_id.value);

    if (!Number.isInteger(id) || id < 1) {
      message("Enter a valid listing ID.", true);
      return;
    }

    try {
      await exportApplicants(id);
      message("Applicant package exported.");
    } catch (error) {
      message(error.message, true);
    }
  }

  async function initialize() {
    try {
      account = await api("/api/ui/me");
      const role = account.role;
      const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);

      $("#hb-role").textContent = roleLabel;
      $("#hb-workspace").textContent = roleLabel;

      const descriptions = {
        graduate: "Browse jobs, apply, and track your applications.",
        employer: "Post job opportunities and manage your applicants.",
        admin: "Review and approve pending job listings."
      };

      const instructions = {
        graduate: "Start by browsing the available opportunities.",
        employer: "Create a listing or view applications for your jobs.",
        admin: "Review listings awaiting publication."
      };

      const startingPage = {
        graduate: "jobs",
        employer: "employer",
        admin: "admin"
      };

      $("#hb-welcome").textContent = descriptions[role];
      $("#hb-next-step").textContent = instructions[role];

      $("#hb-secondary-label").textContent = {
        graduate: "My applications",
        employer: "My listings",
        admin: "Pending listings"
      }[role];

      $$("[data-roles]").forEach((item) => {
        item.hidden = !item.dataset.roles.split(" ").includes(role);
      });

      $("#hb-start").addEventListener("click", () => {
        showPage(startingPage[role]);
      });

      if (role === "graduate") {
        const [jobData, appData] = await Promise.all([
          api("/api/ui/jobs"),
          api("/api/graduates/applications")
        ]);

        jobs = jobData.jobs || [];
        $("#hb-job-count").textContent = jobs.length;
        $("#hb-secondary-count").textContent =
          (appData.applications || []).length;
      }

      if (role === "employer") {
        const data = await api("/api/ui/employer/listings");

        $("#hb-job-label").textContent = "My job listings";
        $("#hb-job-count").textContent = (data.listings || []).length;
        $("#hb-secondary-count").textContent = (data.listings || []).length;
      }

      if (role === "admin") {
        const data = await api("/api/ui/admin/pending");

        $("#hb-job-label").textContent = "Pending listings";
        $("#hb-job-count").textContent = (data.listings || []).length;
        $("#hb-secondary-count").textContent = (data.listings || []).length;
      }

      showPage("overview");
    } catch (error) {
      message(error.message, true);
      $("#hb-welcome").textContent = "Unable to load the dashboard.";
    }
  }

  $$(".hb-tab").forEach((tab) => {
    tab.addEventListener("click", () => showPage(tab.dataset.page));
  });

  $("#hb-search-input").addEventListener("input", renderJobs);
  $("#hb-application-form").addEventListener("submit", submitApplication);
  $("#hb-listing-form").addEventListener("submit", submitListing);
  $("#hb-export-form").addEventListener("submit", submitExport);

  $("#hb-subscribe").addEventListener("click", subscribe);
  $("#hb-refresh-apps").addEventListener("click", loadApplications);
  $("#hb-refresh-notifications").addEventListener("click", loadNotifications);
  $("#hb-refresh-employer").addEventListener("click", loadEmployerListings);
  $("#hb-refresh-admin").addEventListener("click", loadPending);

  $("#hb-close-applicants").addEventListener("click", () => {
    $("#hb-applicant-panel").hidden = true;
  });

  $("#hb-apply-mode").addEventListener("change", (event) => {
    const external = event.target.value === "external";
    $("#hb-external-field").hidden = !external;
    $("#hb-external-field input").required = external;
  });

  $("#hb-close-dialog").addEventListener("click", () => {
    $("#hb-apply-dialog").close();
  });

  $("#hb-cancel-dialog").addEventListener("click", () => {
    $("#hb-apply-dialog").close();
  });

  $("#hb-apply-dialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) {
      event.currentTarget.close();
    }
  });

  const localDate = new Date();
  const year = localDate.getFullYear();
  const month = String(localDate.getMonth() + 1).padStart(2, "0");
  const day = String(localDate.getDate()).padStart(2, "0");

  $("#hb-deadline").min = `${year}-${month}-${day}`;

  window.addEventListener("hashchange", () => {
  const page = window.location.hash.slice(1);
  showPage(page || "overview");
});

initialize();
})();
