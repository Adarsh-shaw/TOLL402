/* TollRail402 Chart.js Analytics Helpers (Emerald + Amber Theme) */
window.TollRailCharts = {
  instances: {},

  destroy(id) {
    if (this.instances[id]) {
      this.instances[id].destroy();
      delete this.instances[id];
    }
  },

  renderActivityChart(canvasId, series) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    this.destroy(canvasId);

    const ctx = canvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 210);
    gradient.addColorStop(0, "rgba(0, 158, 92, 0.16)");
    gradient.addColorStop(1, "rgba(0, 158, 92, 0.0)");

    const labels = series.length ? series.map((s) => s.label) : ["No activity"];
    const successData = series.length ? series.map((s) => s.successful) : [0];
    const failedData = series.length ? series.map((s) => s.failed) : [0];

    this.instances[canvasId] = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Successful",
            data: successData,
            borderColor: "#009e5c",
            backgroundColor: gradient,
            fill: true,
            tension: 0.36,
            borderWidth: 2.2,
            pointRadius: 4,
            pointBackgroundColor: "#009e5c",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
          },
          {
            label: "Failed",
            data: failedData,
            borderColor: "#f59e0b",
            backgroundColor: "transparent",
            fill: false,
            tension: 0.36,
            borderWidth: 2,
            pointRadius: 3.5,
            pointBackgroundColor: "#f59e0b",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: "#64748b",
              font: { family: "Plus Jakarta Sans, sans-serif", size: 11.5 },
            },
          },
          y: {
            beginAtZero: true,
            grid: { color: "#eef3f0" },
            ticks: {
              precision: 0,
              color: "#64748b",
              font: { family: "JetBrains Mono, monospace", size: 11 },
            },
          },
        },
      },
    });
  },

  renderModeComparisonChart(canvasId, comparison) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    this.destroy(canvasId);

    const exactCount = comparison.exact_count || 0;
    const channelCount = comparison.channel_count || 0;
    const hasData = exactCount + channelCount > 0;

    this.instances[canvasId] = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: hasData ? ["Exact Mode", "Channel Mode"] : ["No payments"],
        datasets: [
          {
            data: hasData ? [exactCount, channelCount] : [1],
            backgroundColor: hasData ? ["#009e5c", "#f59e0b"] : ["#e2e8f0"],
            borderColor: "#ffffff",
            borderWidth: 2.5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "66%",
        plugins: {
          legend: { display: false },
        },
      },
    });
  },
};
