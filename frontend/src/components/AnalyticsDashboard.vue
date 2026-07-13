<script setup>
import {
  AlertCircle,
  BarChart3,
  Lightbulb,
  ExternalLink,
  RefreshCw,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

const startDate = ref("28daysAgo");
const endDate = ref("yesterday");
const loading = ref(false);
const error = ref("");
const data = ref(null);

const metrics = computed(() => data.value?.metrics ?? {});
const acquisition = computed(() => data.value?.acquisition ?? []);
const pages = computed(() => data.value?.pages ?? []);
const campaigns = computed(() => data.value?.campaigns ?? []);
const landingPages = computed(() => data.value?.landing_pages ?? []);
const funnelEvents = computed(() => data.value?.funnel_events ?? []);
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
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      start_date: startDate.value,
      end_date: endDate.value,
    });
    const response = await fetch(`/api/analytics/summary?${params.toString()}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Unable to load Google Analytics data");
    data.value = body;
  } catch (failure) {
    data.value = null;
    error.value = failure.message;
  } finally {
    loading.value = false;
  }
}

onMounted(loadAnalytics);
</script>

<template>
  <main
    class="grid min-h-[calc(100vh-112px)] overflow-hidden rounded-lg border border-[oklch(85%_0.012_245)] bg-[oklch(98%_0.004_245)] shadow-sm xl:grid-cols-[300px_minmax(0,1fr)]"
  >
    <aside class="border-b border-[oklch(87%_0.011_245)] bg-[oklch(94%_0.007_245)] p-4 xl:border-b-0 xl:border-r">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
        <BarChart3 :size="14" aria-hidden="true" />
        Google Analytics
      </div>
      <div class="grid gap-4">
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Start date</span>
          <input
            v-model="startDate"
            class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
            type="text"
          />
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">End date</span>
          <input
            v-model="endDate"
            class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
            type="text"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-4 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loading"
          type="button"
          @click="loadAnalytics"
        >
          <RefreshCw :class="{ 'animate-spin': loading }" :size="16" aria-hidden="true" />
          {{ loading ? "Loading" : "Refresh data" }}
        </button>
      </div>

      <div class="mt-6 rounded-md border border-[oklch(83%_0.02_80)] bg-[oklch(96%_0.022_80)] p-3 text-sm text-[oklch(38%_0.055_80)]">
        <div class="font-semibold">Pull setup</div>
        <p class="mt-1 leading-5">
          Configure <span class="font-mono">GA4_PROPERTY_ID</span> and
          <span class="font-mono">GOOGLE_APPLICATION_CREDENTIALS</span>, then refresh this view.
        </p>
      </div>
    </aside>

    <section class="grid min-h-[620px] grid-rows-[auto_1fr] gap-4 overflow-hidden p-4">
      <div class="grid gap-3">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-md border border-[oklch(79%_0.052_30)] bg-[oklch(96%_0.025_30)] p-3 text-sm text-[oklch(36%_0.075_30)]"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>
            <div class="font-semibold">Analytics unavailable</div>
            <div>{{ error }}</div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-sm text-[oklch(48%_0.024_245)]">
          <span class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">
            {{ data ? `${data.start_date} to ${data.end_date}` : "No data loaded" }}
          </span>
          <span v-if="data?.property_id" class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">
            Property {{ data.property_id }}
          </span>
        </div>
      </div>

      <div class="min-h-0 overflow-auto pr-1">
        <div v-if="loading" class="grid gap-3">
          <div class="h-24 animate-pulse rounded-md border border-[oklch(87%_0.012_245)] bg-[oklch(95%_0.007_245)]"></div>
          <div class="h-72 animate-pulse rounded-md border border-[oklch(87%_0.012_245)] bg-[oklch(95%_0.007_245)]"></div>
        </div>

        <div v-else-if="data" class="grid gap-4">
          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4">
              <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">Users</div>
              <div class="mt-2 text-2xl font-semibold">{{ formatNumber(metrics.activeUsers) }}</div>
            </div>
            <div class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4">
              <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">Sessions</div>
              <div class="mt-2 text-2xl font-semibold">{{ formatNumber(metrics.sessions) }}</div>
            </div>
            <div class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4">
              <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">Views</div>
              <div class="mt-2 text-2xl font-semibold">{{ formatNumber(metrics.screenPageViews) }}</div>
            </div>
            <div class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4">
              <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">Conversions</div>
              <div class="mt-2 text-2xl font-semibold">{{ formatNumber(metrics.conversions) }}</div>
            </div>
            <div class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4">
              <div class="text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">Engagement</div>
              <div class="mt-2 text-2xl font-semibold">{{ formatRate(metrics.engagementRate) }}</div>
            </div>
          </div>

          <section class="rounded-md border border-[oklch(84%_0.014_245)] bg-[oklch(99%_0.004_245)]">
            <div class="flex items-center gap-2 border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">
              <Lightbulb :size="16" aria-hidden="true" />
              Founder readout
            </div>
            <div class="grid gap-2 p-4 text-sm">
              <div class="rounded-md bg-[oklch(94%_0.007_245)] px-3 py-2">
                Site conversion rate: <span class="font-semibold">{{ formatRate(signupRate) }}</span>
              </div>
              <div
                v-for="item in recommendations"
                :key="item"
                class="rounded-md border border-[oklch(86%_0.012_245)] px-3 py-2 leading-5"
              >
                {{ item }}
              </div>
            </div>
          </section>

          <section class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)]">
            <div class="border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">Campaign attribution</div>
            <div class="overflow-x-auto">
              <div class="grid min-w-[760px] grid-cols-[minmax(180px,1.2fr)_minmax(160px,1fr)_90px_90px_90px_90px] gap-3 border-b border-[oklch(90%_0.009_245)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
                <span>Source / medium</span>
                <span>Campaign</span>
                <span class="text-right">Sessions</span>
                <span class="text-right">Users</span>
                <span class="text-right">Conv.</span>
                <span class="text-right">Rate</span>
              </div>
              <div class="divide-y divide-[oklch(90%_0.009_245)]">
                <div
                  v-for="row in campaigns"
                  :key="`${row.sourceMedium}-${row.campaign}`"
                  class="grid min-w-[760px] grid-cols-[minmax(180px,1.2fr)_minmax(160px,1fr)_90px_90px_90px_90px] gap-3 px-4 py-3 text-sm"
                >
                  <span class="truncate font-medium">{{ row.sourceMedium }}</span>
                  <span class="truncate text-[oklch(48%_0.024_245)]">{{ row.campaign }}</span>
                  <span class="text-right">{{ formatNumber(row.sessions) }}</span>
                  <span class="text-right">{{ formatNumber(row.activeUsers) }}</span>
                  <span class="text-right">{{ formatNumber(row.conversions) }}</span>
                  <span class="text-right">{{ formatRate(row.conversionRate) }}</span>
                </div>
              </div>
            </div>
          </section>

          <div class="grid gap-4 xl:grid-cols-2">
            <section class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)]">
              <div class="border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">Landing page conversion</div>
              <div class="divide-y divide-[oklch(90%_0.009_245)]">
                <div
                  v-for="row in landingPages"
                  :key="row.landingPage"
                  class="grid grid-cols-[minmax(0,1fr)_74px_74px_74px] gap-3 px-4 py-3 text-sm"
                >
                  <span class="truncate font-medium">{{ row.landingPage }}</span>
                  <span class="text-right">{{ formatNumber(row.sessions) }}</span>
                  <span class="text-right">{{ formatNumber(row.conversions) }}</span>
                  <span class="text-right">{{ formatRate(row.conversionRate) }}</span>
                </div>
              </div>
            </section>

            <section class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)]">
              <div class="border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">Funnel events</div>
              <div class="divide-y divide-[oklch(90%_0.009_245)]">
                <div
                  v-for="row in funnelEvents"
                  :key="row.eventName"
                  class="grid grid-cols-[minmax(0,1fr)_90px_90px_90px] gap-3 px-4 py-3 text-sm"
                >
                  <span class="truncate font-medium">{{ row.eventName }}</span>
                  <span class="text-right">{{ formatNumber(row.eventCount) }}</span>
                  <span class="text-right">{{ formatNumber(row.activeUsers) }}</span>
                  <span class="text-right">{{ formatNumber(row.conversions) }}</span>
                </div>
              </div>
            </section>
          </div>

          <div class="grid gap-4 xl:grid-cols-2">
            <section class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)]">
              <div class="border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">Acquisition</div>
              <div class="divide-y divide-[oklch(90%_0.009_245)]">
                <div
                  v-for="row in acquisition"
                  :key="row.channel"
                  class="grid grid-cols-[minmax(0,1fr)_80px_80px] gap-3 px-4 py-3 text-sm"
                >
                  <span class="truncate font-medium">{{ row.channel }}</span>
                  <span class="text-right">{{ formatNumber(row.sessions) }}</span>
                  <span class="text-right">{{ formatNumber(row.conversions) }}</span>
                </div>
              </div>
            </section>

            <section class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)]">
              <div class="border-b border-[oklch(88%_0.011_245)] px-4 py-3 font-semibold">Top pages</div>
              <div class="divide-y divide-[oklch(90%_0.009_245)]">
                <div
                  v-for="row in pages"
                  :key="row.path"
                  class="grid grid-cols-[minmax(0,1fr)_80px_80px] gap-3 px-4 py-3 text-sm"
                >
                  <span class="truncate font-medium">{{ row.path }}</span>
                  <span class="text-right">{{ formatNumber(row.views) }}</span>
                  <span class="text-right">{{ formatNumber(row.conversions) }}</span>
                </div>
              </div>
            </section>
          </div>
        </div>

        <div v-else class="grid min-h-72 place-items-center rounded-md border border-dashed border-[oklch(82%_0.014_245)] text-center">
          <div class="max-w-md">
            <div class="font-semibold">Connect Google Analytics</div>
            <p class="mt-1 text-sm leading-6 text-[oklch(48%_0.024_245)]">
              Once GA4 credentials are configured, this section shows traffic, conversions, acquisition channels, and top pages.
            </p>
            <a
              class="mt-3 inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)]"
              href="https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart"
              rel="noreferrer"
              target="_blank"
            >
              <ExternalLink :size="15" aria-hidden="true" />
              GA4 Data API quickstart
            </a>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
