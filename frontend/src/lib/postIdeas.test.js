import { expect, it } from "vitest";
import { postIdeasInOrder } from "./postIdeas";

it("waits for each publication before starting the next", async () => {
  const calls = [];
  let release;
  const first = new Promise(resolve => { release = resolve; });
  const pending = postIdeasInOrder([1, 2], async entry => {
    calls.push(entry);
    if (entry === 1) await first;
  });
  expect(calls).toEqual([1]);
  release();
  await pending;
  expect(calls).toEqual([1, 2]);
});

it("stops on failure without retrying or sending the remaining drafts", async () => {
  const posted = [];
  const calls = [];
  await expect(postIdeasInOrder([1, 2, 3], async entry => {
    calls.push(entry);
    if (entry === 2) throw new Error("Publication uncertain");
    posted.push(entry);
  })).rejects.toThrow("Publication uncertain");
  expect(calls).toEqual([1, 2]);
  expect(posted).toEqual([1]);
});
