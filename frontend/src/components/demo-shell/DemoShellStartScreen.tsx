/**
 * Demo Shell Start Screen Component
 *
 * Initial entry point for the demo shell.
 */

interface StartScreenProps {
  onConnect: () => void;
}

export const StartScreen = ({ onConnect }: StartScreenProps) => (
  <div className="demo-screen demo-screen--start">
    <div className="demo-hero">
      <h1 className="demo-title">K8s Accelerator</h1>
      <p className="demo-value-prop">
        Transform Kubernetes operational signals into operator-ready actions
      </p>
      <p className="demo-description">
        Connect to a real Kubernetes cluster and see live diagnostic evidence.
        No fake incidents, no fabricated samples.
      </p>
    </div>
    <div className="demo-cta-area">
      <button
        type="button"
        className="demo-button demo-button--primary"
        onClick={onConnect}
        data-testid="demo-start-button"
      >
        Start real-cluster demo
      </button>
      <p className="demo-cta-hint">Read-only mode · No cluster mutations</p>
    </div>
    <div className="demo-safety-note">
      <p>
        <strong>Safety first:</strong> All actions are preview-only or require operator approval.
        No automatic remediation.
      </p>
    </div>
  </div>
);