(function () {
  "use strict";

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var csrf = csrfMeta ? csrfMeta.content : "";

  // Mobile sidebar
  var menuBtn = document.querySelector("[data-menu]");
  var sidebar = document.getElementById("sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (sidebar.classList.contains("open") && !sidebar.contains(e.target)) sidebar.classList.remove("open");
    });
  }

  // Confirm destructive actions
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Copy-to-clipboard buttons
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var text = btn.getAttribute("data-copy");
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(function () { btn.textContent = old; }, 1400);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done);
    } else {
      var input = btn.parentElement.querySelector("input");
      if (input) { input.select(); document.execCommand("copy"); done(); }
    }
  });

  // Print buttons
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-print]")) window.print();
  });

  // Checkbox toggles: forms marked .js-toggle submit in the background so a
  // long checklist doesn't reload the page on every tick.
  document.addEventListener("change", function (e) {
    var input = e.target;
    var form = input.closest("form.js-toggle");
    if (!form || input.type !== "checkbox") return;
    var data = new FormData(form);
    if (!input.checked) data.delete(input.name);
    input.disabled = true;
    fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "Accept": "application/json", "X-CSRF-Token": csrf },
      credentials: "same-origin"
    })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (res) {
        var li = form.closest("[data-item]");
        if (li) {
          li.classList.toggle("done", !!res.done);
          var meta = li.querySelector(".meta");
          if (meta) meta.textContent = res.meta || "";
        }
        if (res.progress) updateProgress(res.progress);
      })
      .catch(function () {
        input.checked = !input.checked;
        alert("Couldn't save that change. Refresh the page and try again.");
      })
      .finally(function () { input.disabled = false; });
  });

  function updateProgress(progress) {
    Object.keys(progress).forEach(function (key) {
      var el = document.querySelector('[data-progress="' + key + '"]');
      if (!el) return;
      var p = progress[key];
      var pct = p.total ? Math.round((100 * p.done) / p.total) : 0;
      var bar = el.querySelector(".progress-bar");
      el.querySelector(".progress-bar > span").style.width = pct + "%";
      bar.classList.toggle("complete", p.total > 0 && p.done === p.total);
      el.querySelector(".progress-text").textContent = p.done + "/" + p.total;
    });
  }

  // Event form: adapt labels, run of show and checklists to the event type.
  var typeSelect = document.getElementById("f-event_type");
  var profilesEl = document.getElementById("event-type-profiles");
  if (typeSelect && profilesEl) {
    var profiles = JSON.parse(profilesEl.textContent);
    var profileFor = function (name) { return profiles[name] || profiles[""]; };
    var prev = profileFor(typeSelect.value);
    var applyLabels = function (p) {
      var peopleLabel = document.querySelector('label[for="f-honorees"]');
      if (peopleLabel) peopleLabel.textContent = p.people_label;
      [["f-venue_label", p.venue_label || "Venue"], ["f-venue2_label", p.venue2_label || "Second location"]].forEach(function (pair) {
        var input = document.getElementById(pair[0]);
        if (input) input.placeholder = pair[1];
      });
    };
    applyLabels(prev);
    typeSelect.addEventListener("change", function () {
      var next = profileFor(typeSelect.value);
      applyLabels(next);
      // Swap the run of show only if it's empty or still the previous starter.
      var ros = document.getElementById("f-run_of_show");
      if (ros && (!ros.value.trim() || ros.value.trim() === (prev.run_of_show || "").trim())) {
        ros.value = next.run_of_show || "";
      }
      document.querySelectorAll('input[name="templates"]').forEach(function (box) {
        box.checked = next.checklists.indexOf(parseInt(box.value, 10)) !== -1;
      });
      prev = next;
    });
  }

  // Invoice line-item editor
  var lines = document.querySelector("[data-lines]");
  if (lines) {
    var tbody = lines.querySelector("tbody");
    var template = document.getElementById("line-template");
    var fmt = function (n) {
      return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    var num = function (el) { var v = parseFloat(el && el.value); return isNaN(v) ? 0 : v; };
    var cents = function (n) { return Math.round(n * 100) / 100; };
    var recalc = function () {
      var subtotal = 0, taxable = 0;
      tbody.querySelectorAll("tr").forEach(function (tr) {
        var line = cents(num(tr.querySelector("[name=item_quantity]")) * num(tr.querySelector("[name=item_price]")));
        tr.querySelector(".line-total").textContent = fmt(line);
        subtotal += line;
        var tax = tr.querySelector("[name=item_taxable_flag]");
        if (tax && tax.checked) taxable += line;
      });
      var discount = Math.min(num(document.querySelector("[name=discount]")), subtotal);
      if (subtotal > 0 && taxable > 0) taxable -= (discount * taxable) / subtotal;
      var tax = cents((taxable * num(document.querySelector("[name=tax_rate]"))) / 100);
      var set = function (key, v) { var el = document.querySelector('[data-total="' + key + '"]'); if (el) el.textContent = fmt(v); };
      set("subtotal", subtotal);
      set("discount", -discount);
      set("tax", tax);
      set("total", cents(subtotal - discount + tax));
    };
    // Checkbox values don't post when unchecked, so mirror each one into a
    // hidden field that always posts in row order.
    var syncTaxable = function (tr) {
      var box = tr.querySelector("[name=item_taxable_flag]");
      tr.querySelector("[name=item_taxable]").value = box.checked ? "1" : "0";
    };
    lines.addEventListener("input", recalc);
    lines.addEventListener("change", function (e) {
      var tr = e.target.closest("tr");
      if (tr && e.target.name === "item_taxable_flag") syncTaxable(tr);
      recalc();
    });
    document.querySelectorAll("[name=discount], [name=tax_rate]").forEach(function (el) { el.addEventListener("input", recalc); });
    lines.addEventListener("click", function (e) {
      if (e.target.closest("[data-remove-line]")) {
        e.target.closest("tr").remove();
        recalc();
      }
    });
    var addBtn = document.querySelector("[data-add-line]");
    if (addBtn) addBtn.addEventListener("click", function () {
      tbody.appendChild(template.content.cloneNode(true));
      var rows = tbody.querySelectorAll("tr");
      rows[rows.length - 1].querySelector("[name=item_description]").focus();
      recalc();
    });
    recalc();
  }
})();
