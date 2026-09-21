(function () {
  var presentationToggle = document.getElementById("presentation-toggle");
  if (presentationToggle) {
    var presentationKey = "subscript-clean-view";
    var setPresentationMode = function (enabled) {
      document.body.classList.toggle("presentation-mode", enabled);
      presentationToggle.setAttribute("aria-pressed", String(enabled));
      presentationToggle.textContent = enabled ? "Show settings" : "Clean view";
      try { window.localStorage.setItem(presentationKey, enabled ? "1" : "0"); } catch (_) {}
    };
    var storedPresentation = false;
    try { storedPresentation = window.localStorage.getItem(presentationKey) === "1"; } catch (_) {}
    presentationToggle.addEventListener("click", function () {
      setPresentationMode(!document.body.classList.contains("presentation-mode"));
    });
    setPresentationMode(storedPresentation);
  }

  var publishing = document.getElementById("publishing-form");
  if (publishing) {
    var destinationNames = {youtube:"YouTube",tiktok:"TikTok",instagram:"Instagram",facebook:"Facebook",twitter:"X",rumble:"Rumble"};
    var selectedDestinations = function () {
      return Object.keys(destinationNames).filter(function (key) {
        var toggle = publishing.querySelector('[name="' + key + '_enabled"]');
        return toggle && toggle.checked;
      });
    };
    var syncDestinations = function () {
      publishing.querySelectorAll("[data-platform]").forEach(function (card) {
        var toggle = card.querySelector('.switch input');
        var panel = card.querySelector('.platform-settings');
        if (toggle && panel) {
          panel.hidden = !toggle.checked;
          panel.id = "settings-" + card.dataset.platform;
          toggle.setAttribute("aria-controls", panel.id);
          toggle.setAttribute("aria-expanded", String(toggle.checked));
        }
      });
      var chosen = selectedDestinations();
      document.getElementById("post-copy-destinations").textContent = chosen.length ? "Drafts for: " + chosen.map(function (key) {return destinationNames[key];}).join(", ") : "First, turn on the destinations you want below.";
    };
    publishing.querySelectorAll('.switch input').forEach(function (toggle) {
      toggle.addEventListener("change", function () {
        syncDestinations();
        document.getElementById("post-copy-preview").hidden = true;
        document.getElementById("post-copy-preview-status").textContent = "Destinations changed. Generate fresh samples, then save publishing settings to apply your choices.";
      });
    });
    syncDestinations();
    var generateButton = document.getElementById("generate-post-preview");
    generateButton.addEventListener("click", async function () {
      var status = document.getElementById("post-copy-preview-status");
      var output = document.getElementById("post-copy-preview");
      output.hidden = true;
      generateButton.disabled = true;
      status.textContent = "Generating sample drafts…";
      try {
        var data = new FormData(publishing);
        data.set("platforms", selectedDestinations().join(","));
        var response = await fetch("/post-copy/preview", {method:"POST",body:data});
        var result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not generate drafts. Try again.");
        output.replaceChildren();
        result.drafts.forEach(function (draft) {
          var card = document.createElement("section"); card.className = "control-panel form-grid";
          var heading = document.createElement("h4"); heading.textContent = draft.platform; card.appendChild(heading);
          [["Title",draft.title],["Description / caption",draft.description],["Tags",draft.tags.join(", ")]].forEach(function (field) {
            var label = document.createElement("label"); label.textContent = field[0];
            var text = document.createElement("textarea"); text.readOnly = true; text.value = field[1];
            label.appendChild(text);card.appendChild(label);
          });
          output.appendChild(card);
        });
        output.hidden = false;
        status.textContent = "Samples ready. Nothing was saved or published. For clip-specific drafts, go to Review.";
      } catch (error) { status.textContent = error.message; }
      finally { generateButton.disabled = false; }
    });
  }
  var connectForm = document.getElementById("youtube-connect-form");
  if (connectForm) connectForm.addEventListener("submit", function () {
    var connectButton = document.querySelector('[form="youtube-connect-form"]');
    if (connectButton) {
      connectButton.disabled = true;
      connectButton.textContent = "Finish Google sign-in in your browser…";
    }
  });
  function revealCaptureSetup() {
    if (window.location.hash === "#capture-setup") {
      if (document.body.classList.contains("presentation-mode") && presentationToggle) {
        presentationToggle.click();
      }
      var details = document.querySelector("#capture-setup > details");
      if (details) details.open = true;
    }
  }
  window.addEventListener("hashchange", revealCaptureSetup);
  revealCaptureSetup();
  var form = document.getElementById("clip-form");
  if (form) {
    var drop = document.getElementById("drop-zone");
    var input = document.getElementById("file-input");
    var label = document.getElementById("file-label");
    var custom = document.getElementById("custom-fields");
    var busy = document.getElementById("busy");
    var btn = document.getElementById("clip-btn");
    var customRadio = form.querySelector('input[name="mode"][value="custom"]');
    var localPath = document.getElementById("local-path");
    var submitting = false;
    function startSelectedVideo() {
      if (localPath) localPath.value = "";
      var automatic = document.getElementById("auto-start");
      if (automatic && automatic.checked) form.requestSubmit();
    }

    function setFileName(file) {
      if (!label) return;
      label.textContent = file ? file.name : "No file chosen";
    }

    function syncCustom() {
      if (!custom || !customRadio) return;
      custom.hidden = !customRadio.checked;
    }

    if (input) {
      input.addEventListener("change", function () {
        setFileName(input.files && input.files[0]);
        if (input.files && input.files[0]) startSelectedVideo();
      });
    }

    if (drop && input) {
      ["dragenter", "dragover"].forEach(function (ev) {
        drop.addEventListener(ev, function (e) {
          e.preventDefault();
          drop.classList.add("dragover");
        });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        drop.addEventListener(ev, function (e) {
          e.preventDefault();
          drop.classList.remove("dragover");
        });
      });
      drop.addEventListener("drop", function (e) {
        var files = e.dataTransfer && e.dataTransfer.files;
        if (!files || !files.length) return;
        var dt = new DataTransfer();
        dt.items.add(files[0]);
        input.files = dt.files;
        setFileName(files[0]);
        startSelectedVideo();
      });
      drop.addEventListener("click", function (e) {
        if (e.target.closest("label") || e.target === input) return;
        input.click();
      });
      drop.addEventListener("keydown", function (e) {
        if (e.target === drop && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          input.click();
        }
      });
    }

    form.querySelectorAll('input[name="mode"]').forEach(function (radio) {
      radio.addEventListener("change", syncCustom);
    });
    syncCustom();

    form.addEventListener("submit", function (event) {
      if (submitting) { event.preventDefault(); return; }
      if (!(input && input.files && input.files.length) && !(localPath && localPath.value.trim())) {
        event.preventDefault();
        label.textContent = "Choose a video above to begin.";
        drop.focus();
        return;
      }
      submitting = true;
      form.setAttribute("aria-busy", "true");
      if (busy) busy.hidden = false;
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Making your clip…";
      }
    });
  }

  // Branding panel
  var brandForm = document.getElementById("brand-form");
  if (brandForm) {
    var opacity = document.getElementById("brand-opacity");
    var opacityVal = document.getElementById("brand-opacity-val");
    var logoInput = document.getElementById("brand-logo-input");
    var preview = document.getElementById("brand-preview");
    var previewWrap = document.getElementById("brand-preview-wrap");
    var previewEmpty = document.getElementById("brand-preview-empty");
    var saveBtn = document.getElementById("brand-save");
    var objectUrl = null;

    function syncOpacity() {
      if (!opacity || !opacityVal) return;
      opacityVal.textContent = opacity.value;
    }

    if (opacity) {
      opacity.addEventListener("input", syncOpacity);
      syncOpacity();
    }

    var musicVol = document.getElementById("music-volume");
    var musicVolVal = document.getElementById("music-volume-val");
    function syncMusicVol() {
      if (!musicVol || !musicVolVal) return;
      musicVolVal.textContent = Number(musicVol.value).toFixed(2);
    }
    if (musicVol) {
      musicVol.addEventListener("input", syncMusicVol);
      syncMusicVol();
    }

    if (logoInput) {
      logoInput.addEventListener("change", function () {
        var file = logoInput.files && logoInput.files[0];
        if (!file || !preview) return;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(file);
        preview.src = objectUrl;
        if (previewWrap) previewWrap.hidden = false;
        if (previewEmpty) previewEmpty.hidden = true;
      });
    }

    brandForm.addEventListener("submit", function () {
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving…";
      }
    });
  }

  // Publishing save state
  var publishingForm = document.getElementById("publishing-form");
  if (publishingForm) {
    publishingForm.addEventListener("submit", function () {
      var publishingBtn = publishingForm.querySelector('button[type="submit"]');
      if (publishingBtn) {
        publishingBtn.disabled = true;
        publishingBtn.textContent = "Saving destinations…";
      }
    });
  }

  // Guided automated workflow setup: one visible step at a time, with a clear
  // reason to continue or a clear correction to make before continuing.
  var workflowWizard = document.getElementById("workflow-wizard");
  if (workflowWizard) {
    var workflowForm = document.getElementById("workflow-setup-form");
    var workflowSteps = Array.prototype.slice.call(workflowWizard.querySelectorAll("[data-wizard-step]"));
    var workflowStepNumber = document.getElementById("workflow-step-number");
    var workflowStepStatus = document.getElementById("workflow-step-status");
    var workflowCurrent = 0;
    var replayReady = workflowWizard.querySelector('[data-wizard-check="replay-ready"]');
    var startConfirm = workflowWizard.querySelector('[data-wizard-check="start-confirm"]');
    var reviewModeInput = workflowWizard.querySelector('[name="review_mode"]');
    var profileToggles = Array.prototype.slice.call(workflowWizard.querySelectorAll("[data-profile-toggle]"));
    var profileHelp = document.getElementById("workflow-profile-help");
    var flowMessages = {
      0: "Check the box after the replay is saved.",
      1: "Enter a replay folder and a shortcut such as ctrl+shift+c.",
      2: "Choose a clip length between 5 and 300 seconds.",
      3: "Choose at least one posting profile for automatic publishing.",
      4: "Confirm the trigger order before arming the workflow."
    };
    var flowReadyMessages = {
      0: "Replay ready. Now connect SubScript to that folder.",
      1: "Connection details look good. Now choose delivery.",
      2: "Delivery choice saved. Now build the posting profiles.",
      3: "Profiles ready. Now make a safe test preview.",
      4: "You are ready. Test first, then save and start when the preview looks right."
    };
    function workflowHotkeyValid(value) {
      return /^(?:(?:ctrl|alt|shift)\+)+[a-z0-9]$/.test(String(value || "").trim().toLowerCase());
    }
    function workflowStepValid(index) {
      if (index === 0) return !!(replayReady && replayReady.checked);
      if (index === 1) {
        var folder = workflowWizard.querySelector('[name="folder"]');
        var hotkey = workflowWizard.querySelector('[name="hotkey"]');
        return !!(folder && folder.value.trim() && hotkey && workflowHotkeyValid(hotkey.value));
      }
      if (index === 2) {
        var seconds = Number((workflowWizard.querySelector('[name="seconds"]') || {}).value);
        return Number.isFinite(seconds) && seconds >= 5 && seconds <= 300;
      }
      if (index === 3) {
        return !reviewModeInput || reviewModeInput.value !== "automatic" || profileToggles.some(function (toggle) { return toggle.checked; });
      }
      return !!(startConfirm && startConfirm.checked);
    }
    function renderWorkflowStep() {
      workflowSteps.forEach(function (section, index) {
        section.hidden = index !== workflowCurrent;
      });
      if (workflowStepNumber) workflowStepNumber.textContent = String(workflowCurrent + 1);
      if (workflowStepStatus) workflowStepStatus.textContent = workflowStepValid(workflowCurrent) ? flowReadyMessages[workflowCurrent] : flowMessages[workflowCurrent];
      var automatic = !reviewModeInput || reviewModeInput.value === "automatic";
      if (profileHelp) profileHelp.textContent = automatic
        ? "Choose the destinations that should receive each finished clip. Automatic publishing requires at least one profile. Titles, descriptions, tags, and formats are optional."
        : "Review-first mode can run without posting profiles. Add destinations now if you want the saved workflow ready for later automatic publishing.";
      profileToggles.forEach(function (toggle) {
        var card = toggle.closest(".automation-profile");
        var fields = card && card.querySelector(".profile-fields");
        if (card) card.classList.toggle("profile-selected", toggle.checked);
        if (fields) {
          fields.hidden = !toggle.checked;
          fields.querySelectorAll("input, select, textarea").forEach(function (control) { control.disabled = !toggle.checked; });
        }
      });
      workflowWizard.querySelectorAll("[data-wizard-next]").forEach(function (button) {
        button.disabled = !workflowStepValid(workflowCurrent);
      });
      workflowWizard.querySelectorAll("[data-wizard-back]").forEach(function (button) {
        button.hidden = workflowCurrent === 0;
      });
      var startButton = workflowWizard.querySelector("[data-start-flow]");
      if (startButton) startButton.disabled = !workflowStepValid(4) || !workflowStepValid(3);
      workflowWizard.querySelectorAll("[data-wizard-message]").forEach(function (message) {
        var key = message.getAttribute("data-wizard-message");
        var relevant = (workflowCurrent === 0 && key === "replay-ready") ||
          (workflowCurrent === 1 && key === "connection") ||
          (workflowCurrent === 2 && key === "delivery") ||
          (workflowCurrent === 3 && key === "profiles") ||
          (workflowCurrent === 4 && key === "start-confirm");
        message.hidden = !relevant || workflowStepValid(workflowCurrent);
        if (relevant && !workflowStepValid(workflowCurrent)) message.textContent = flowMessages[workflowCurrent];
      });
    }
    workflowWizard.querySelectorAll("[data-wizard-next]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!workflowStepValid(workflowCurrent) || workflowCurrent >= workflowSteps.length - 1) return;
        workflowCurrent += 1;
        renderWorkflowStep();
        var heading = workflowSteps[workflowCurrent].querySelector("h3");
        if (heading) { heading.tabIndex = -1; heading.focus(); }
      });
    });
    workflowWizard.querySelectorAll("[data-wizard-back]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (workflowCurrent <= 0) return;
        workflowCurrent -= 1;
        renderWorkflowStep();
      });
    });
    workflowWizard.querySelectorAll("input, select").forEach(function (input) {
      input.addEventListener("input", renderWorkflowStep);
      input.addEventListener("change", renderWorkflowStep);
    });
    if (workflowForm) workflowForm.addEventListener("submit", function (event) {
      var submitter = event.submitter;
      if (submitter && submitter.value === "save_and_start" && (!workflowStepValid(3) || !workflowStepValid(4))) {
        event.preventDefault();
        renderWorkflowStep();
      }
    });
    renderWorkflowStep();
  }

  // Dedicated automated-profile slideshow. It keeps one profile's folder,
  // trigger, delivery, and posting plan together, then returns to the studio.
  var automationForm = document.getElementById("automation-profile-form");
  if (automationForm) {
    var automationSlides = Array.prototype.slice.call(automationForm.querySelectorAll("[data-automation-step]"));
    var automationNav = Array.prototype.slice.call(document.querySelectorAll(".automation-slide-nav li"));
    var automationNumber = document.getElementById("automation-step-number");
    var automationStatus = document.getElementById("automation-step-status");
    var automationCurrent = 0;
    var automationMode = automationForm.querySelector('[name="review_mode"]');
    var automationProfiles = Array.prototype.slice.call(automationForm.querySelectorAll("[data-profile-toggle]"));
    var automationConfirm = automationForm.querySelector("[data-automation-confirm]");
    var automationMessages = {
      0: "Enter a profile name and a real VOD folder before continuing.",
      1: "Use a shortcut such as ctrl+shift+c and a clip length from 5 to 300 seconds.",
      2: "Choose how this profile should handle each finished clip.",
      3: "Automatic delivery needs at least one destination.",
      4: "Confirm the trigger order before saving and starting this profile."
    };
    var automationReady = {
      0: "Identity saved. Now set the trigger.",
      1: "Trigger saved. Now choose delivery.",
      2: "Delivery saved. Now build the destinations.",
      3: "Posting plan ready. Test and save this profile.",
      4: "Ready. Test first, then save or start this profile."
    };
    function automationHotkeyValid(value) {
      return /^(?:(?:ctrl|alt|shift)\+)+[a-z0-9]$/.test(String(value || "").trim().toLowerCase());
    }
    function automationValid(index) {
      if (index === 0) {
        var name = automationForm.querySelector('[name="profile_name"]');
        var folder = automationForm.querySelector('[name="folder"]');
        return !!(name && name.value.trim() && folder && folder.value.trim());
      }
      if (index === 1) {
        var hotkey = automationForm.querySelector('[name="hotkey"]');
        var seconds = Number((automationForm.querySelector('[name="seconds"]') || {}).value);
        return !!(hotkey && automationHotkeyValid(hotkey.value) && Number.isFinite(seconds) && seconds >= 5 && seconds <= 300);
      }
      if (index === 3) {
        return !automationMode || automationMode.value !== "automatic" || automationProfiles.some(function (toggle) { return toggle.checked; });
      }
      if (index === 4) return !!(automationConfirm && automationConfirm.checked);
      return true;
    }
    function renderAutomationStep() {
      automationSlides.forEach(function (slide, index) { slide.hidden = index !== automationCurrent; });
      automationNav.forEach(function (item, index) { item.classList.toggle("is-current", index === automationCurrent); });
      if (automationNumber) automationNumber.textContent = String(automationCurrent + 1);
      if (automationStatus) automationStatus.textContent = automationValid(automationCurrent) ? automationReady[automationCurrent] : automationMessages[automationCurrent];
      automationProfiles.forEach(function (toggle) {
        var card = toggle.closest(".automation-profile");
        var fields = card && card.querySelector(".profile-fields");
        if (card) card.classList.toggle("profile-selected", toggle.checked);
        if (fields) fields.querySelectorAll("input, select, textarea").forEach(function (control) { control.disabled = !toggle.checked; });
      });
      var help = document.getElementById("automation-profile-help");
      if (help) help.textContent = automationMode && automationMode.value === "automatic"
        ? "Choose at least one destination for this folder. Each selected destination keeps its own format and post copy."
        : "Review-first mode can run without posting destinations. Add them now if you want this profile ready for later automatic delivery.";
      automationForm.querySelectorAll("[data-automation-next]").forEach(function (button) { button.disabled = !automationValid(automationCurrent); });
      automationForm.querySelectorAll("[data-automation-back]").forEach(function (button) { button.hidden = automationCurrent === 0; });
      automationForm.querySelectorAll("[data-automation-message]").forEach(function (message) {
        var key = message.getAttribute("data-automation-message");
        var relevant = (automationCurrent === 0 && key === "identity") || (automationCurrent === 1 && key === "trigger") || (automationCurrent === 3 && key === "profiles") || (automationCurrent === 4 && key === "finish");
        message.classList.toggle("is-visible", relevant && !automationValid(automationCurrent));
        if (relevant && !automationValid(automationCurrent)) message.textContent = automationMessages[automationCurrent];
      });
      var start = automationForm.querySelector("[data-automation-start]");
      if (start) start.disabled = !automationValid(3) || !automationValid(4);
    }
    automationForm.querySelectorAll("[data-automation-next]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!automationValid(automationCurrent) || automationCurrent >= automationSlides.length - 1) return;
        automationCurrent += 1; renderAutomationStep();
        var heading = automationSlides[automationCurrent].querySelector("h3");
        if (heading) { heading.tabIndex = -1; heading.focus(); }
      });
    });
    automationForm.querySelectorAll("[data-automation-back]").forEach(function (button) {
      button.addEventListener("click", function () { if (automationCurrent > 0) { automationCurrent -= 1; renderAutomationStep(); } });
    });
    automationForm.querySelectorAll("input, select, textarea").forEach(function (input) {
      input.addEventListener("input", renderAutomationStep); input.addEventListener("change", renderAutomationStep);
    });
    automationForm.addEventListener("submit", function (event) {
      var submitter = event.submitter;
      if (submitter && submitter.value === "save_and_start" && (!automationValid(3) || !automationValid(4))) {
        event.preventDefault(); renderAutomationStep();
      }
    });
    renderAutomationStep();
  }

  // Keep the compact workflow bar in sync with the visible stage.
  var workflowLinks = Array.prototype.slice.call(
    document.querySelectorAll(".workflow-nav a")
  );
  if (workflowLinks.length && "IntersectionObserver" in window) {
    var sections = workflowLinks
      .map(function (link) {
        return document.querySelector(link.getAttribute("href"));
      })
      .filter(Boolean);
    var stageObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          workflowLinks.forEach(function (link) {
            link.classList.toggle(
              "active",
              link.getAttribute("href") === "#" + entry.target.id
            );
          });
        });
      },
      { rootMargin: "-18% 0px -65% 0px", threshold: 0 }
    );
    sections.forEach(function (section) {
      stageObserver.observe(section);
    });
  }

  // Live hotkey status card
  var liveCard = document.getElementById("live-hotkey-card");
  if (!liveCard) return;

  var startBtn = document.getElementById("live-start");
  var stopBtn = document.getElementById("live-stop");
  var armedLabel = document.getElementById("live-armed-label");
  var liveDot = document.getElementById("live-dot");
  var liveMsg = document.getElementById("live-msg");

  function applyStatus(data) {
    var armed = !!(data && data.armed);
    if (armedLabel) {
      armedLabel.textContent = armed ? "Armed" : "Not armed";
    }
    if (liveDot) {
      liveDot.classList.toggle("on", armed);
      liveDot.classList.toggle("off", !armed);
    }
    if (startBtn) startBtn.disabled = armed;
    if (stopBtn) stopBtn.disabled = !armed;
    if (liveMsg) {
      if (data && data.last_error) {
        liveMsg.textContent = "Last error: " + data.last_error;
      } else if (data && data.last_ok) {
        liveMsg.textContent =
          data.last_ok +
          (data.fire_count ? " (fires: " + data.fire_count + ")" : "");
      } else if (data && data.source_hint) {
        liveMsg.textContent = data.source_hint;
      }
    }
  }

  function refresh() {
    fetch("/live/status")
      .then(function (r) {
        return r.json();
      })
      .then(applyStatus)
      .catch(function () {});
  }

  function post(url) {
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
    fetch(url, { method: "POST" })
      .then(function (r) {
        return r.json();
      })
      .then(applyStatus)
      .catch(function (err) {
        if (liveMsg) liveMsg.textContent = "Request failed: " + err;
        refresh();
      });
  }

  if (startBtn) {
    startBtn.addEventListener("click", function () {
      post("/live/start");
    });
  }
  if (stopBtn) {
    stopBtn.addEventListener("click", function () {
      post("/live/stop");
    });
  }

  refresh();
  setInterval(refresh, 4000);
})();
