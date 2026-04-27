import { createContext, useContext } from "react";
import { DRIP_DEFAULT } from "../lib/formatters";

export type Preferences = {
  dripThreshold: number;
  setDripThreshold: (value: number) => void;
};

export const PreferencesContext = createContext<Preferences>({
  dripThreshold: DRIP_DEFAULT,
  setDripThreshold: () => {},
});

export const usePreferences = (): Preferences => useContext(PreferencesContext);
