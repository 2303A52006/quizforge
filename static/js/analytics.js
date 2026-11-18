/* Draws the teacher analytics charts with Chart.js. Data comes from the json_script tag. */
(function () {
  "use strict";

  var dataEl = document.getElementById("chart-data");
  if (!dataEl || typeof Chart === "undefined") {
    return;
  }
  var data = JSON.parse(dataEl.textContent);

  function colourFor(value) {
    if (value < 50) {
      return "rgba(220, 53, 69, 0.75)"; // red = weak
    }
    if (value < 75) {
      return "rgba(255, 193, 7, 0.85)"; // yellow
    }
    return "rgba(25, 135, 84, 0.75)"; // green
  }

  var percentScale = { beginAtZero: true, max: 100, title: { display: true, text: "% correct" } };

  new Chart(document.getElementById("distributionChart"), {
    type: "bar",
    data: {
      labels: data.distributionLabels,
      datasets: [
        {
          label: "Students",
          data: data.distributionCounts,
          backgroundColor: "rgba(13, 110, 253, 0.75)"
        }
      ]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: "Percentage band" } },
        y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Students" } }
      }
    }
  });

  new Chart(document.getElementById("topicChart"), {
    type: "bar",
    data: {
      labels: data.topicLabels,
      datasets: [
        {
          label: "% correct",
          data: data.topicValues,
          backgroundColor: data.topicValues.map(colourFor)
        }
      ]
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: { x: percentScale }
    }
  });

  new Chart(document.getElementById("questionChart"), {
    type: "bar",
    data: {
      labels: data.questionLabels,
      datasets: [
        {
          label: "% correct",
          data: data.questionValues,
          backgroundColor: data.questionValues.map(colourFor)
        }
      ]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: percentScale }
    }
  });
})();
