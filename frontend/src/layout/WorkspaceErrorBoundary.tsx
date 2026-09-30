import { Component, type ReactNode } from "react";

/** Keep workspace failures out of the persistent navigation/header. */
export class WorkspaceErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <section role="alert" className="surface-card space-y-3 p-5">
          <h1 className="text-lg font-semibold">Unable to load this workspace.</h1>
          <p>Reload the page to try again, or choose another workspace.</p>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Reload workspace
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}
