/*
 * Quiz-taking page.
 *  - Shows a countdown. The SERVER owns the real deadline; this is only a display.
 *  - Autosaves each answer to the server as soon as an option is chosen.
 *  - Auto-submits the form when the countdown reaches zero.
 */
(function () {
  "use strict";

  var root = document.getElementById("quiz-root");
  if (!root) {
    return;
  }

  var form = document.getElementById("quiz-form");
  var timerEl = document.getElementById("timer");
  var statusEl = document.getElementById("save-status");
  var answeredEl = document.getElementById("answered-count");
  var submitBtn = document.getElementById("submit-btn");
  var saveUrl = root.dataset.saveUrl;
  var csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
  var totalQuestions = form.querySelectorAll(".question-card").length;

  var remainingAtLoad = parseInt(root.dataset.remaining, 10);
  var loadedPerf = performance.now();
  var loadedClock = Date.now();
  var submitting = false;

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function secondsLeft() {
    // Use whichever clock shows more time passed, so pausing one clock cannot stretch the display.
    var elapsedPerf = (performance.now() - loadedPerf) / 1000;
    var elapsedClock = (Date.now() - loadedClock) / 1000;
    return Math.max(0, Math.ceil(remainingAtLoad - Math.max(elapsedPerf, elapsedClock)));
  }

  function countAnswered() {
    return form.querySelectorAll("input[type=radio]:checked").length;
  }

  function updateAnswered() {
    answeredEl.textContent = countAnswered();
  }

  function submitNow() {
    if (submitting) {
      return;
    }
    submitting = true;
    submitBtn.disabled = true;
    form.submit();
  }

  function renderTimer() {
    var left = secondsLeft();
    var minutes = Math.floor(left / 60);
    var seconds = left % 60;
    timerEl.textContent = pad(minutes) + ":" + pad(seconds);
    timerEl.classList.toggle("text-danger", left <= 60);
    if (left <= 0) {
      clearInterval(handle);
      statusEl.textContent = "Time is up - submitting...";
      submitNow();
    }
  }

  function saveAnswer(questionId, optionId) {
    statusEl.textContent = "Saving...";
    var body = new URLSearchParams();
    body.set("question", questionId);
    body.set("option", optionId);
    fetch(saveUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: body
    })
      .then(function (response) {
        if (response.ok) {
          statusEl.textContent = "Saved";
        } else if (response.status === 403 || response.status === 409) {
          // Server says time is up (or already submitted): finish the attempt.
          statusEl.textContent = "Time is up - submitting...";
          submitNow();
        } else {
          statusEl.textContent = "Not saved yet (will be sent on submit)";
        }
      })
      .catch(function () {
        statusEl.textContent = "Offline (will be sent on submit)";
      });
  }

  form.addEventListener("change", function (event) {
    var input = event.target;
    if (input && input.type === "radio") {
      saveAnswer(input.name.replace("q_", ""), input.value);
      updateAnswered();
    }
  });

  Array.prototype.forEach.call(form.querySelectorAll("[data-clear]"), function (button) {
    button.addEventListener("click", function () {
      var questionId = button.getAttribute("data-clear");
      Array.prototype.forEach.call(
        form.querySelectorAll("input[name=q_" + questionId + "]"),
        function (radio) {
          radio.checked = false;
        }
      );
      saveAnswer(questionId, "");
      updateAnswered();
    });
  });

  form.addEventListener("submit", function (event) {
    if (submitting) {
      return;
    }
    var unanswered = totalQuestions - countAnswered();
    if (unanswered > 0) {
      var ok = window.confirm(
        "You have " + unanswered + " unanswered question(s). Submit anyway?"
      );
      if (!ok) {
        event.preventDefault();
        return;
      }
    }
    submitting = true;
    submitBtn.disabled = true;
  });

  var handle = setInterval(renderTimer, 500);
  renderTimer();
  updateAnswered();
})();
