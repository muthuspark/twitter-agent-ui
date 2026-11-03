<script setup>
import { RefreshCw } from "@lucide/vue";
import { computed, onActivated, ref } from "vue";
import ReportTable from "./ReportTable.vue";

const startDate = ref("28daysAgo");
const endDate = ref("yesterday");
const loading = ref(false);
const error = ref("");
const data = ref(null);

const metrics = computed(() => data.value?.metrics ?? {});
const recommendations = computed(() => data.value?.recommendations ?? []);

function formatNumber(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat().format(number);
}

function formatRate(value) {
  const number = Number(value || 0);
  return `${Math.round(number * 100)}%`;
}

const signupRate = computed(() => {
  const sessions = Number(metrics.value.sessions || 0);
  if (!sessions) return 0;
  return Number(metrics.value.conversions || 0) / sessions;
});

async function loadAnalytics() {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      start_date: startDate.value,
      end_date: endDate.value,
    });
    const response = await fetch(`/api/analytics/summary?${params.toString()}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(body.detail || "Unable to load Google Analytics data");
    data.value = body;
  } catch (failure) {
    data.value = null;
    error.value = failure.message;
  } finally {
    loading.value = false;
  }
}

const numberColumn = (key, label) => ({
  key,
  label,
  numeric: true,
  format: formatNumber,
});
const rateColumn = (key, label) => ({
  key,
  label,
  numeric: true,
  format: formatRate,
});
const reports = [
  {
    title: "Campaign attribution",
    key: "campaigns",
    columns: [
      { key: "sourceMedium", label: "Source / medium" },
      { key: "campaign", label: "Campaign" },
      numberColumn("sessions", "Sessions"),
      numberColumn("activeUsers", "Users"),
      numberColumn("conversions", "Conversions"),
      rateColumn("conversionRate", "Rate"),
    ],
  },
  {
    title: "Landing pages",
    key: "landing_pages",
    columns: [
      { key: "landingPage", label: "Page" },
      numberColumn("sessions", "Sessions"),
      numberColumn("conversions", "Conversions"),
      rateColumn("conversionRate", "Rate"),
    ],
  },
  {
    title: "Funnel events",
    key: "funnel_events",
    columns: [
      { key: "eventName", label: "Event" },
      numberColumn("eventCount", "Events"),
      numberColumn("activeUsers", "Users"),
      numberColumn("conversions", "Conversions"),
    ],
  },
  {
    title: "Acquisition",
    key: "acquisition",
    columns: [
      { key: "channel", label: "Channel" },
      numberColumn("sessions", "Sessions"),
      numberColumn("conversions", "Conversions"),
    ],
  },
  {
    title: "Top pages",
    key: "pages",
    columns: [
      { key: "path", label: "Page" },
      numberColumn("views", "Views"),
      numberColumn("conversions", "Conversions"),
    ],
  },
];
const summaryColumns = [
  numberColumn("activeUsers", "Users"),
  numberColumn("sessions", "Sessions"),
  numberColumn("screenPageViews", "Views"),
  numberColumn("conversions", "Conversions"),
  rateColumn("engagementRate", "Engagement"),
];

onActivated(loadAnalytics);
</script>

<template>
  <main class="analytics-view">
    <header class="analytics-heading">
      <h2 class="text-2xl font-bold">Analytics</h2>
      <form class="analytics-controls" @submit.prevent="loadAnalytics">
        <label
          >From<input
            v-model="startDate"
            type="text"
            class="min-h-11 border border-rule-strong bg-paper px-3"
            aria-label="Start date"
        /></label>
        <label
          >To<input
            v-model="endDate"
            type="text"
            class="min-h-11 border border-rule-strong bg-paper px-3"
            aria-label="End date"
        /></label>
        <button class="button" :disabled="loading" type="submit">
          <RefreshCw
            :class="{ 'animate-spin': loading }"
            :size="16"
            aria-hidden="true"
          />{{ loading ? "Loading…" : "Refresh" }}
        </button>
      </form>
    </header>
    <div v-if="error" class="analytics-error" role="alert">{{ error }}</div>
    <details v-if="error" class="analytics-setup">
      <summary>Connect Google Analytics</summary>
      <p>
        Set <code>GA4_PROPERTY_ID</code> and
        <code>GOOGLE_APPLICATION_CREDENTIALS</code> on the server.
      </p>
      <a
        href="https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart"
        target="_blank"
        rel="noreferrer"
        class="inline-flex min-h-11 items-center underline underline-offset-4"
        >Setup guide</a
      >
    </details>
    <div
      v-if="loading"
      class="grid gap-3"
      role="status"
      aria-label="Loading analytics"
    >
      <div class="h-24 animate-pulse rounded-sm bg-paper-shade"></div>
      <div class="h-72 animate-pulse rounded-sm bg-paper-shade"></div>
    </div>
    <div v-else-if="data" class="analytics-report">
      <dl class="analytics-summary">
        <div
          v-for="column in summaryColumns"
          :key="column.key"
          class="summary-metric"
        >
          <dt class="text-sm text-muted">{{ column.label }}</dt>
          <dd class="mt-2 text-2xl font-semibold">
            {{ column.format(metrics[column.key]) }}
          </dd>
        </div>
      </dl>
      <section class="analytics-insights" aria-labelledby="insights-title">
        <h3 id="insights-title" class="font-semibold">
          Conversion rate: {{ formatRate(signupRate) }}
        </h3>
        <ul v-if="recommendations.length" class="mt-3 grid gap-2 text-sm">
          <li v-for="item in recommendations" :key="item">{{ item }}</li>
        </ul>
      </section>
      <div class="analytics-tables">
        <ReportTable
          v-for="report in reports"
          :key="report.key"
          :title="report.title"
          :columns="report.columns"
          :rows="data[report.key] || []"
        />
      </div>
      <details v-if="data.property_id" class="text-sm text-muted">
        <summary>Report details</summary>
        <p>
          Property {{ data.property_id }} · {{ data.start_date }} to
          {{ data.end_date }}
        </p>
      </details>
    </div>
    <p v-else-if="!error" class="analytics-empty">No analytics data</p>
  </main>
</template>

<style scoped>
.analytics-view {
  padding-block: 1.5rem 3rem;
}
.analytics-heading,
.analytics-controls {
  display: flex;
  align-items: end;
  gap: 0.75rem;
}
.analytics-heading {
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
}
.analytics-controls label {
  display: grid;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: var(--muted);
}
.analytics-controls input {
  max-width: 10rem;
  color: var(--ink);
}
.analytics-error {
  padding: 1rem;
  border: 1px solid var(--danger-rule);
  background: var(--danger-wash);
  color: var(--danger);
  margin-bottom: 1rem;
  font-size: 0.875rem;
}
.analytics-setup {
  max-width: 65ch;
  padding-block: 1rem;
  font-size: 0.875rem;
}
.analytics-setup p {
  margin-top: 0.75rem;
}
.analytics-tables {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 2rem;
}
.analytics-insights {
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--rule);
}
.analytics-empty {
  padding-block: 4rem;
  text-align: center;
  color: var(--muted);
}
@media (min-width: 1100px) {
  .analytics-tables {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .analytics-tables > :first-child {
    grid-column: 1 / -1;
  }
}
@media (max-width: 639px) {
  .analytics-controls {
    width: 100%;
    flex-wrap: wrap;
  }
  .analytics-controls label {
    flex: 1;
    min-width: 0;
  }
  .analytics-controls input {
    max-width: none;
  }
  .analytics-controls .button {
    width: 100%;
  }
}
</style>
