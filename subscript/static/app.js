(function () {
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
        label.textContent = "Choose a video or enter a local file path to begin.";
        drop.focus();
        return;
      }
      submitting = true;
      form.setAttribute("aria-busy", "true");
      if (busy) busy.hidden = false;
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Working…";
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
