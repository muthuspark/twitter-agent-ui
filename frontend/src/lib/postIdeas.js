// Keep browser publishing sequential. A rejected or uncertain write stops the batch.
export async function postIdeasInOrder(entries, publish) {
  for (const entry of entries) await publish(entry);
}
