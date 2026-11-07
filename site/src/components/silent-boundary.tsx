import { Component, type ReactNode } from 'react'

/** Renders nothing if its children crash, so an add-on never breaks the page around it. */
export class SilentBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    console.warn('IrisClick add-on hidden after an error:', error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}
