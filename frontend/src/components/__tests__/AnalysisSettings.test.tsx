import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AnalysisSettings } from "../AnalysisSettings";
import { PreferencesContext } from "../../state/usePreferences";

it("explains the heuristic and changes only the local threshold, preserving scope in the Income link", () => {
  const setDripThreshold = vi.fn();
  render(<MemoryRouter initialEntries={["/data?tab=settings&account=ISA&period=YTD"]}>
    <PreferencesContext.Provider value={{ dripThreshold: 1000, setDripThreshold, accountFilter: "ISA", setAccountFilter: vi.fn() }}>
      <AnalysisSettings />
    </PreferencesContext.Provider>
  </MemoryRouter>);
  expect(screen.getByText(/not proven dividends/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "250.50" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  expect(setDripThreshold).toHaveBeenCalledWith(250.5);
  expect(screen.getByRole("link", { name: "View Income proxy" })).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&tab=income");
});
