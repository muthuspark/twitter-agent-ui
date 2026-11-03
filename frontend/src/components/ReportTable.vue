<script setup>
defineProps({
  title: { type: String, required: true },
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
});
</script>

<template>
  <div class="report-table">
    <table>
      <caption>
        {{
          title
        }}
      </caption>
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            scope="col"
            :class="{ numeric: column.numeric }"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td
            v-for="column in columns"
            :key="column.key"
            :class="{ numeric: column.numeric }"
          >
            {{
              column.format ? column.format(row[column.key]) : row[column.key]
            }}
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length" class="empty-cell">No data</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.report-table {
  min-width: 0;
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
caption {
  text-align: left;
  padding-bottom: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--ink);
}
th,
td {
  text-align: left;
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
th {
  font-weight: 500;
  color: var(--muted);
  white-space: nowrap;
}
th:first-child,
td:first-child {
  padding-left: 0;
}
th:last-child,
td:last-child {
  padding-right: 0;
}
td {
  max-width: 24rem;
  overflow-wrap: anywhere;
}
.numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.empty-cell {
  color: var(--muted);
}
</style>
