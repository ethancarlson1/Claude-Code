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

  // Confirm destructive actions (on the form, or on the button that submitted it)
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm") ||
      (e.submitter && e.submitter.getAttribute("data-confirm-button"));
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Crew pay: select all and a running total of what's selected
  var payForm = document.querySelector("[data-pay-form]");
  if (payForm) {
    var boxes = payForm.querySelectorAll('input[name="ids"]');
    var updateTotal = function () {
      var count = 0, total = 0;
      boxes.forEach(function (b) { if (b.checked) { count += 1; total += parseFloat(b.getAttribute("data-amount")) || 0; } });
      var c = payForm.querySelector("[data-selected-count]");
      var t = payForm.querySelector("[data-selected-total]");
      if (c) c.textContent = count;
      if (t) t.textContent = "$" + total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    payForm.addEventListener("change", function (e) {
      if (e.target.matches("[data-check-all]")) {
        boxes.forEach(function (b) { b.checked = e.target.checked; });
      }
      updateTotal();
    });
    updateTotal();
  }

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
      // Dollars off, or a percentage of the subtotal.
      var rawDiscount = Math.max(num(document.querySelector("[name=discount]")), 0);
      var discountType = document.querySelector("[name=discount_type]");
      var percent = discountType && discountType.value === "percent";
      var discount = Math.min(percent ? cents((subtotal * rawDiscount) / 100) : rawDiscount, subtotal);
      var discountLabel = document.querySelector("[data-discount-label]");
      if (discountLabel) discountLabel.textContent = percent && rawDiscount ? "(" + rawDiscount + "%)" : "";
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
    document.querySelectorAll("[name=discount], [name=tax_rate], [name=discount_type]").forEach(function (el) {
      el.addEventListener("input", recalc);
      el.addEventListener("change", recalc);
    });
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

  // Event request form: keep a draft on this device so nothing typed is lost
  // (a closed tab, a dropped connection, an upload that was too big...).
  var storage = {
    get: function (k) { try { return JSON.parse(window.localStorage.getItem(k) || "null"); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
    drop: function (k) { try { window.localStorage.removeItem(k); } catch (e) { /* private mode */ } }
  };
  document.querySelectorAll("[data-clear-draft]").forEach(function (el) {
    storage.drop("draft:" + el.getAttribute("data-clear-draft"));
  });
  var draftForm = document.querySelector("form[data-autosave]");
  if (draftForm) {
    var draftKey = "draft:" + draftForm.getAttribute("data-autosave");
    var skip = function (el) { return !el.name || el.type === "file" || el.type === "hidden" || el.name === "website"; };
    var saveDraft = function () {
      var data = {};
      Array.prototype.forEach.call(draftForm.elements, function (el) {
        if (skip(el)) return;
        if (el.type === "checkbox" || el.type === "radio") {
          if (el.checked) (data[el.name] = data[el.name] || []).push(el.value);
        } else if (el.value) {
          data[el.name] = el.value;
        }
      });
      storage.set(draftKey, data);
    };
    var saved = draftForm.getAttribute("data-fresh") === "1" ? storage.get(draftKey) : null;
    if (saved && Object.keys(saved).length) {
      Array.prototype.forEach.call(draftForm.elements, function (el) {
        if (skip(el) || !(el.name in saved)) return;
        if (el.type === "checkbox" || el.type === "radio") el.checked = saved[el.name].indexOf(el.value) !== -1;
        else el.value = saved[el.name];
      });
      var note = document.querySelector("[data-restore-note]");
      if (note) note.hidden = false;
    }
    var timer;
    draftForm.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(saveDraft, 400); });
    draftForm.addEventListener("change", saveDraft);
    document.querySelectorAll("[data-clear-form]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        storage.drop(draftKey);
        draftForm.reset();
        btn.closest("[data-restore-note]").hidden = true;
      });
    });
    // Catch uploads that are too big before sending, instead of losing the whole form.
    var fileInput = draftForm.querySelector("input[type=file][data-max-bytes]");
    if (fileInput) fileInput.addEventListener("change", function () {
      var max = parseInt(fileInput.getAttribute("data-max-bytes"), 10);
      var maxFiles = parseInt(fileInput.getAttribute("data-max-files"), 10);
      var total = 0;
      Array.prototype.forEach.call(fileInput.files, function (f) { total += f.size; });
      var message = "";
      if (fileInput.files.length > maxFiles) message = "Please attach up to " + maxFiles + " files.";
      else if (total > max * 0.95) message = "These files add up to more than " + Math.floor(max / 1048576) +
        " MB. Attach fewer or smaller files, or email them to us after sending the form.";
      fileInput.setCustomValidity(message);
      if (message) fileInput.reportValidity();
    });
  }
})();
