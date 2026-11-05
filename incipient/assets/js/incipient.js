/* Incipient Artistic Ventures — site script
   Vanilla, no dependencies. Everything here is progressive enhancement:
   the pages read fine with scripting off. */
(function () {
  "use strict";

  /* ---------- navigation ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  /* ---------- audio players ----------
     Markup: <div class="player" data-src="previews/x.mp3" data-title="…">
     The native <audio> element is created here so the page degrades to a
     plain list of titles when scripting is off. One track plays at a time. */
  var players = Array.prototype.slice.call(document.querySelectorAll(".player[data-src]"));
  var current = null;
  var RING = 163.4; // 2π·26

  function fmt(s) {
    if (!isFinite(s) || s < 0) return "0:00";
    var m = Math.floor(s / 60), r = Math.floor(s % 60);
    return m + ":" + (r < 10 ? "0" : "") + r;
  }

  players.forEach(function (el) {
    var audio = document.createElement("audio");
    audio.preload = "metadata";
    audio.src = el.getAttribute("data-src");
    el.appendChild(audio);

    var btn = el.querySelector(".player__btn");
    var seek = el.querySelector(".player__seek");
    var cur = el.querySelector(".player__cur");
    var dur = el.querySelector(".player__dur");
    var fill = el.querySelector(".ring .fill");
    var status = el.querySelector(".player__status");

    function setProgress(p) {
      if (fill) fill.style.strokeDashoffset = String(RING - RING * Math.max(0, Math.min(1, p)));
      if (seek) seek.value = String(Math.round(p * 1000));
    }

    audio.addEventListener("loadedmetadata", function () {
      if (dur) dur.textContent = fmt(audio.duration);
      if (status) status.textContent = "";
    });
    audio.addEventListener("timeupdate", function () {
      if (cur) cur.textContent = fmt(audio.currentTime);
      if (audio.duration) setProgress(audio.currentTime / audio.duration);
    });
    audio.addEventListener("ended", function () {
      el.classList.remove("is-playing");
      btn.setAttribute("aria-label", "Play " + el.getAttribute("data-title"));
      setProgress(0);
      if (cur) cur.textContent = "0:00";
    });
    audio.addEventListener("error", function () {
      el.classList.add("is-missing");
      el.classList.remove("is-playing");
      if (status) status.textContent = "Preview file not uploaded yet (expected at " + el.getAttribute("data-src") + ").";
      btn.setAttribute("aria-disabled", "true");
    });

    btn.addEventListener("click", function () {
      if (el.classList.contains("is-missing")) return;
      if (audio.paused) {
        if (current && current !== audio) { current.pause(); }
        var p = audio.play();
        if (p && p.catch) { p.catch(function () { /* autoplay policy or missing file: the error handler covers it */ }); }
        current = audio;
      } else {
        audio.pause();
      }
    });
    audio.addEventListener("play", function () {
      players.forEach(function (o) { if (o !== el) { o.classList.remove("is-playing"); } });
      el.classList.add("is-playing");
      btn.setAttribute("aria-label", "Pause " + el.getAttribute("data-title"));
    });
    audio.addEventListener("pause", function () {
      el.classList.remove("is-playing");
      btn.setAttribute("aria-label", "Play " + el.getAttribute("data-title"));
    });
    if (seek) {
      seek.addEventListener("input", function () {
        if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration;
      });
    }
  });

  /* ---------- store: preview cart ----------
     Nothing is charged. Checkout is not connected; the drawer says so. */
  var shelf = document.querySelector(".shelf");
  if (shelf) {
    var cart = [];
    var pill = document.querySelector(".cart-pill");
    var drawer = document.querySelector(".drawer");
    var scrim = document.querySelector(".scrim");
    var list = drawer.querySelector(".drawer__body ul");
    var empty = drawer.querySelector(".drawer__empty");
    var totalEl = drawer.querySelector(".drawer__total b");
    var countEl = pill.querySelector("b");

    function money(n) { return "$" + n.toFixed(2); }
    function render() {
      list.innerHTML = "";
      var total = 0;
      cart.forEach(function (item, i) {
        total += item.price;
        var li = document.createElement("li");
        li.innerHTML = "<span>" + item.title + "<small>" + item.format + "</small></span>" +
          "<span>" + money(item.price) + "</span>" +
          "<button class=\"btn btn--small\" type=\"button\" data-remove=\"" + i + "\">Remove</button>";
        list.appendChild(li);
      });
      empty.hidden = cart.length > 0;
      totalEl.textContent = money(total);
      countEl.textContent = cart.length + (cart.length === 1 ? " item" : " items");
      pill.hidden = cart.length === 0;
    }
    function openDrawer(open) {
      drawer.setAttribute("aria-hidden", open ? "false" : "true");
      scrim.classList.toggle("is-on", open);
      if (open) drawer.querySelector(".drawer__close").focus();
    }
    shelf.addEventListener("click", function (e) {
      var b = e.target.closest("[data-add]");
      if (!b) return;
      var card = b.closest(".release");
      var checked = card.querySelector("input[type=radio]:checked");
      var price = parseFloat(checked ? checked.getAttribute("data-price") : b.getAttribute("data-price"));
      cart.push({ title: card.getAttribute("data-title"), format: checked ? checked.getAttribute("data-label") : "Digital", price: price });
      render();
      b.textContent = "Added";
      setTimeout(function () { b.textContent = "Add to cart"; }, 1200);
    });
    shelf.addEventListener("change", function (e) {
      var r = e.target;
      if (r.type !== "radio") return;
      var card = r.closest(".release");
      var priceEl = card.querySelector(".release__price");
      if (priceEl) priceEl.textContent = money(parseFloat(r.getAttribute("data-price")));
    });
    pill.addEventListener("click", function () { openDrawer(true); });
    drawer.addEventListener("click", function (e) {
      if (e.target.closest(".drawer__close")) openDrawer(false);
      var r = e.target.closest("[data-remove]");
      if (r) { cart.splice(parseInt(r.getAttribute("data-remove"), 10), 1); render(); }
    });
    scrim.addEventListener("click", function () { openDrawer(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && drawer.getAttribute("aria-hidden") === "false") openDrawer(false);
    });
    render();
  }

  /* ---------- exchange: filters and listing details ---------- */
  var board = document.querySelector(".board");
  if (board) {
    var filters = document.querySelectorAll(".filters button");
    var listings = board.querySelectorAll(".listing");
    var emptyNote = board.querySelector(".board-empty");
    filters.forEach(function (f) {
      f.addEventListener("click", function () {
        filters.forEach(function (o) { o.setAttribute("aria-pressed", o === f ? "true" : "false"); });
        var cat = f.getAttribute("data-filter");
        var shown = 0;
        listings.forEach(function (l) {
          var show = cat === "all" || l.getAttribute("data-cat") === cat;
          l.hidden = !show;
          if (show) shown++;
        });
        if (emptyNote) emptyNote.hidden = shown > 0;
      });
    });
    var modal = document.querySelector("dialog.modal");
    if (modal && typeof modal.showModal === "function") {
      function openListing(l) {
        modal.querySelector(".modal__title").textContent = l.querySelector("h3").textContent;
        modal.querySelector(".modal__cat").textContent = l.querySelector(".listing__cat").textContent;
        modal.querySelector(".modal__price").textContent = l.querySelector(".listing__price").firstChild.textContent.trim();
        modal.querySelector(".modal__desc").textContent = l.getAttribute("data-desc") || l.querySelector("p").textContent;
        modal.querySelector(".modal__cond").textContent = l.getAttribute("data-condition") || "";
        modal.querySelector(".modal__where").textContent = l.getAttribute("data-where") || "";
        modal.showModal();
      }
      board.addEventListener("click", function (e) {
        var l = e.target.closest(".listing");
        if (l) openListing(l);
      });
      modal.addEventListener("click", function (e) {
        if (e.target.closest(".modal__close") || e.target === modal) modal.close();
      });
    }
  }
})();
