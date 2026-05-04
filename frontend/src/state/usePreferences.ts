import { createContext, useContext } from "react";
import { DRIP_DEFAULT } from "../lib/formatters";

export type AccountFilter = "all" | string;

export type Preferences = {
  dripThreshold: number;
  setDripThreshold: (value: number) => void;
  accountFilter: AccountFilter;
  setAccountFilter: (value: AccountFilter) => void;
};

export const PreferencesContext = createContext<Preferences>({
  dripThreshold: DRIP_DEFAULT,
  setDripThreshold: () => {},
  accountFilter: "all",
  setAccountFilter: () => {},
});

export const usePreferences = (): Preferences => useContext(PreferencesContext);
