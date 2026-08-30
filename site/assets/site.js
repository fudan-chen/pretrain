(() => {
  const now = Date.now();
  document.querySelectorAll("[data-freshness]").forEach((element) => {
    const timestamp = Date.parse(element.dataset.freshness);
    const threshold = Number(element.dataset.threshold || 18);
    if (!Number.isFinite(timestamp)) {
      element.textContent = "数据时间未知";
      element.classList.add("freshness-stale");
      return;
    }
    const hours = Math.max(0, (now - timestamp) / 3_600_000);
    let label = "新鲜";
    let className = "freshness-fresh";
    if (hours > threshold * 3) {
      label = "陈旧";
      className = "freshness-stale";
    } else if (hours > threshold) {
      label = "延迟";
      className = "freshness-delayed";
    }
    element.textContent = `${label} · 数据距今约 ${hours.toFixed(1)} 小时`;
    element.classList.add(className);
  });
})();
