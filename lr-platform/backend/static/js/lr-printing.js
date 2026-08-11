(function () {
  "use strict";

  function json(url, options) {
    return fetch(url, Object.assign({
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" }
    }, options || {})).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.error || "Remote printing request failed");
        });
      }
      return response.json();
    });
  }

  function button(label, handler) {
    var element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.style.cssText = "margin:8px 6px 0 0;padding:8px 12px;border:0;border-radius:6px;cursor:pointer";
    element.addEventListener("click", handler);
    return element;
  }

  function notification(job, sessionId, connectionId) {
    var panel = document.createElement("div");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Remote print job");
    panel.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483647;max-width:420px;padding:16px;background:#fff;color:#17202a;border:1px solid #ccd6dd;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.2);font:14px Segoe UI,sans-serif";
    var title = document.createElement("strong");
    title.textContent = "Remote print job received";
    panel.appendChild(title);
    var name = document.createElement("div");
    name.textContent = job.document_name || "PDF document";
    name.style.cssText = "margin-top:6px;overflow-wrap:anywhere";
    panel.appendChild(name);

    function finishLater() {
      window.setTimeout(function () {
        json("/api/printing/jobs/" + encodeURIComponent(job.job_id) + "/result", {
          method: "POST",
          body: JSON.stringify({
            session_id: sessionId,
            connection_id: connectionId,
            state: "saved"
          })
        }).catch(function () {});
      }, 30000);
      panel.remove();
    }

    panel.appendChild(button("Open PDF", function () {
      window.open(job.open_url, "_blank", "noopener,noreferrer");
      finishLater();
    }));
    panel.appendChild(button("Download PDF", function () {
      window.location.assign(job.download_url);
      finishLater();
    }));
    panel.appendChild(button("Cancel", function () {
      json("/api/printing/jobs/" + encodeURIComponent(job.job_id) + "/cancel", {
        method: "POST",
        body: "{}"
      }).catch(function () {});
      panel.remove();
    }));
    document.body.appendChild(panel);
  }

  function start(sessionId, options) {
    if (!sessionId) {
      throw new Error("An LR session ID is required for browser printing");
    }
    options = options || {};
    var connectionId = self.crypto.randomUUID();
    var stopped = false;
    var retryInterval = Math.max(Number(options.retryInterval || 2500), 1000);

    function register() {
      return json("/api/printing/clients/register", {
        method: "POST",
        body: JSON.stringify({
          session_id: String(sessionId),
          connection_id: connectionId,
          client_type: "browser",
          capabilities: { open_pdf: true, download_pdf: true },
          printers: []
        })
      });
    }

    function poll() {
      if (stopped) { return; }
      var query = new URLSearchParams({ session_id: String(sessionId), wait: "25" });
      json("/api/printing/browser/" + connectionId + "/next?" + query.toString())
        .then(function (result) {
          if (result.job) { notification(result.job, String(sessionId), connectionId); }
        })
        .then(function () { if (!stopped) { poll(); } })
        .catch(function () {
          return register().finally(function () {
            if (!stopped) { window.setTimeout(poll, retryInterval); }
          });
        });
    }

    register().then(poll);
    return {
      connectionId: connectionId,
      stop: function () {
        stopped = true;
        var query = new URLSearchParams({ session_id: String(sessionId) });
        fetch("/api/printing/clients/" + connectionId + "?" + query.toString(), {
          method: "DELETE",
          credentials: "same-origin"
        }).catch(function () {});
      }
    };
  }

  window.LRRemotePrinting = { start: start };
}());
