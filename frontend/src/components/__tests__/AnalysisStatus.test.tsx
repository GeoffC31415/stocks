import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisStatus } from "../AnalysisStatus";

describe("AnalysisStatus", () => {
  it("exposes metric reasons but does not invent a retry or repair link", () => {
    render(<AnalysisStatus kind="unavailable" title="Return unavailable"
      reasons={[{ code: "short", message: "Two observations needed.", action_href: null }]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Two observations needed.");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("offers retry only for a fetch failure", () => {
    const retry = vi.fn();
    render(<AnalysisStatus kind="error" title="Could not load" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("renders a repair link only when supplied", () => {
    render(<AnalysisStatus kind="empty" title="No snapshots" reasons={[
      { code: "empty", message: "Import a snapshot.", action_href: "/data?tab=import" },
    ]} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/data?tab=import");
  });
});
