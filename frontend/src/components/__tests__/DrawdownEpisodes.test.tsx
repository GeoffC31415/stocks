import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import type { DrawdownEpisode } from "../../lib/api";
import { DrawdownEpisodes } from "../DrawdownEpisodes";

const episode: DrawdownEpisode = { id: "2026-01-01:2026-01-05", peak_date: "2026-01-01", trough_date: "2026-01-05",
  end_date: "2026-02-01", depth_pct: -20, recovery_date: "2026-02-01", recovery_interval_start: "2026-01-20",
  days_to_trough: 4, elapsed_days: 31, observations: 4 };
it("labels observed recovery bounds and links a chart-only window without changing financial scope", () => {
  render(<MemoryRouter initialEntries={["/portfolio?tab=performance&account=ISA&period=YTD"]}>
    <DrawdownEpisodes available episodes={[episode]} />
  </MemoryRouter>);
  expect(screen.getByText("-20.00%")).toBeInTheDocument();
  expect(screen.getByText(/20 Jan 2026 – 1 Feb 2026/)).toBeInTheDocument();
  expect(screen.getByRole("link")).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&tab=performance&episode=2026-01-01%3A2026-01-05#performance-chart");
});
it("does not invent recovery for an unfinished episode", () => {
  render(<MemoryRouter><DrawdownEpisodes available episodes={[{ ...episode, recovery_date: null, recovery_interval_start: null }]} /></MemoryRouter>);
  expect(screen.getByText(/Not observed by 1 Feb 2026/)).toBeInTheDocument();
});
it("hides legacy episode numbers when the common chain is unavailable", () => {
  render(<MemoryRouter><DrawdownEpisodes available={false} episodes={[episode]}
    reasons={[{ code: "invalid_return_chain", message: "Broken interval.", action_href: null }]} /></MemoryRouter>);
  expect(screen.getByText("Broken interval.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
it("distinguishes a valid flat history from unavailable data", () => {
  render(<MemoryRouter><DrawdownEpisodes available episodes={[]} /></MemoryRouter>);
  expect(screen.getByText("No observed drawdown episodes in this window.")).toBeInTheDocument();
});
