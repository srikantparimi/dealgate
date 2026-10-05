import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignatureTab } from '../../pages/v2/sow-workspace/SignatureTab';
import { HandoffTab } from '../../pages/v2/sow-workspace/HandoffTab';
import type { WorkspaceSnapshot } from '../../pages/v2/sow-workspace/readiness';
import type { MeResponse } from '../../api/client';

const api = vi.hoisted(() => ({ uploadSignedSowFile: vi.fn(), verifySignedSow: vi.fn(),
  getHandoffGate: vi.fn(), getDeliveryAcceptance: vi.fn(), recordDeliveryAcceptance: vi.fn(), releaseSignedSow: vi.fn() }));
vi.mock('../../api/client', async original => ({ ...await original<object>(), ...api }));
const viewer = { id: 'owner', groups: ['SystemAdmin'] } as MeResponse;
const signed = { id: 'upload', package_id: 'package', verify_status: 'verified', released_at: null };
const readyGate = { ok: true, checks: { internal_signoff: true, client_execution: true,
  delivery_acceptance: true, approvals_current: true, not_superseded: true }, reasons: [] };
function snapshot(changes: Record<string, unknown> = {}): WorkspaceSnapshot {
  return { deal: { id: 'deal', owner_id: 'owner' }, sow: { id: 'version', file_hash: 'hash1234' },
    approvalPackage: { id: 'package', sow_version_id: 'version', status: 'ready_to_sign', required_functions: [], approvals: [] },
    agreements: [], signedSow: null, gmModel: null, ...changes } as unknown as WorkspaceSnapshot;
}
beforeEach(() => {
  vi.clearAllMocks();
  api.getHandoffGate.mockResolvedValue(readyGate);
  api.getDeliveryAcceptance.mockResolvedValue(null);
  api.uploadSignedSowFile.mockResolvedValue({ ...signed, verify_status: 'pending' });
  api.verifySignedSow.mockResolvedValue(signed);
  api.recordDeliveryAcceptance.mockResolvedValue({ id: 'acceptance', staffing_confirmed: true,
    billing_setup_confirmed: true, po_confirmed: true });
  api.releaseSignedSow.mockResolvedValue({ ...signed, released_at: '2026-10-03' });
});

describe('workspace real execution actions', () => {
  it('uploads an explicitly attested file and verifies separately; never offers fake Send', async () => {
    const refresh = vi.fn();
    render(<SignatureTab snap={snapshot()} viewer={viewer} refresh={refresh} />);
    expect(screen.queryByRole('button', { name: 'Send for signature' })).not.toBeInTheDocument();
    const file = new File(['signed bytes'], 'executed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Executed document'), { target: { files: [file] } });
    expect(screen.getByRole('button', { name: 'Upload executed document' })).toBeDisabled();
    fireEvent.click(screen.getByLabelText('This document contains signature evidence'));
    fireEvent.click(screen.getByRole('button', { name: 'Upload executed document' }));
    await waitFor(() => expect(api.uploadSignedSowFile).toHaveBeenCalledWith('package', file, true));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Verify executed document' }));
    await waitFor(() => expect(api.verifySignedSow).toHaveBeenCalledWith('package'));
  });

  it('preserves failed upload inputs for explicit retry and displays server error', async () => {
    api.uploadSignedSowFile.mockRejectedValueOnce(new Error('409 Package changed'));
    render(<SignatureTab snap={snapshot()} viewer={viewer} />);
    const file = new File(['bytes'], 'executed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Executed document'), { target: { files: [file] } });
    fireEvent.click(screen.getByLabelText('This document contains signature evidence'));
    fireEvent.click(screen.getByRole('button', { name: 'Upload executed document' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('409 Package changed');
    fireEvent.click(screen.getByRole('button', { name: 'Upload executed document' }));
    await waitFor(() => expect(api.uploadSignedSowFile).toHaveBeenCalledTimes(2));
  });

  it('denies nonowners and superseded or different source packages', () => {
    const { rerender } = render(<SignatureTab snap={snapshot()} viewer={{ ...viewer, id: 'other', groups: ['Finance'] }} />);
    expect(screen.queryByLabelText('Executed document')).not.toBeInTheDocument();
    rerender(<SignatureTab snap={snapshot({ approvalPackage: { id: 'package', sow_version_id: 'old',
      status: 'ready_to_sign', superseded_by: 'new', approvals: [] } })} viewer={viewer} />);
    expect(screen.queryByLabelText('Executed document')).not.toBeInTheDocument();
    expect(screen.getByText(/superseded|different SOW version/i)).toBeInTheDocument();
  });

  it('does not refresh a new route when an old upload completes', async () => {
    let resolve!: (value: unknown) => void;
    api.uploadSignedSowFile.mockReturnValue(new Promise(done => { resolve = done; }));
    const refresh = vi.fn();
    const { rerender } = render(<SignatureTab snap={snapshot()} viewer={viewer} refresh={refresh} />);
    fireEvent.change(screen.getByLabelText('Executed document'), { target: { files: [new File(['x'], 'x.pdf')] } });
    fireEvent.click(screen.getByLabelText('This document contains signature evidence'));
    fireEvent.click(screen.getByRole('button', { name: 'Upload executed document' }));
    rerender(<SignatureTab snap={snapshot({ approvalPackage: null })} viewer={viewer} refresh={refresh} />);
    await act(async () => resolve(signed));
    expect(refresh).not.toHaveBeenCalled();
  });

  it('never infers notifications or acceptance from release timestamp', async () => {
    render(<HandoffTab snap={snapshot({ signedSow: { ...signed, released_at: '2026-10-03' } })} viewer={viewer} />);
    await waitFor(() => expect(api.getDeliveryAcceptance).toHaveBeenCalledWith('package'));
    expect(screen.queryByText('Notified')).not.toBeInTheDocument();
    expect(screen.queryByText('Acknowledged')).not.toBeInTheDocument();
    expect(screen.queryByText('Configured')).not.toBeInTheDocument();
    expect(await screen.findByText('Not recorded')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Distribution receipts' })).toHaveAttribute('href', '/handoffs/package');
  });

  it('records explicit acceptance booleans and uses server gate for release', async () => {
    api.getHandoffGate.mockResolvedValueOnce({ ...readyGate, ok: false, reasons: ['Delivery acceptance missing'] });
    render(<HandoffTab snap={snapshot({ signedSow: signed })} viewer={viewer} />);
    expect(await screen.findByText('Delivery acceptance missing')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Release handoff' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Record delivery acceptance' })).toBeDisabled();
    for (const name of ['Staffing confirmed', 'Billing setup confirmed', 'PO confirmed']) fireEvent.click(screen.getByLabelText(name));
    fireEvent.change(screen.getByLabelText('Acceptance notes'), { target: { value: 'Reviewed source' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record delivery acceptance' }));
    await waitFor(() => expect(api.recordDeliveryAcceptance).toHaveBeenCalledWith('package', {
      staffing_confirmed: true, billing_setup_confirmed: true, po_confirmed: true, notes: 'Reviewed source' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Release handoff' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Release handoff' }));
    await waitFor(() => expect(api.releaseSignedSow).toHaveBeenCalledWith('package'));
  });

  it.each(['blocked', 'unsigned', 'declined', 'expired'])('preserves actual %s verification state and reason', status => {
    render(<SignatureTab snap={snapshot({ signedSow: { ...signed, verify_status: status, verify_reason: 'Source requires review' } })} viewer={viewer} />);
    expect(screen.getByText(`Verification: ${status}`)).toBeInTheDocument();
    expect(screen.getByText('Source requires review')).toBeInTheDocument();
  });

  it('does not offer acceptance to Sales or release to nonowner Delivery', async () => {
    const { rerender } = render(<HandoffTab snap={snapshot()} viewer={{ ...viewer, groups: ['Sales'] }} />);
    await screen.findByText('Not recorded');
    expect(screen.queryByRole('button', { name: 'Record delivery acceptance' })).not.toBeInTheDocument();
    rerender(<HandoffTab snap={snapshot()} viewer={{ ...viewer, id: 'delivery', groups: ['Delivery'] }} />);
    expect(screen.queryByRole('button', { name: 'Release handoff' })).not.toBeInTheDocument();
  });

  it('reports gate fetch failure and cannot release from unknown state', async () => {
    api.getHandoffGate.mockRejectedValueOnce(new Error('Gate unavailable'));
    render(<HandoffTab snap={snapshot()} viewer={viewer} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Gate unavailable');
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Release handoff' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh handoff' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Release handoff' })).toBeEnabled());
  });

  it('ignores old package handoff gate after route change', async () => {
    let resolve!: (value: unknown) => void;
    api.getHandoffGate.mockReturnValueOnce(new Promise(done => { resolve = done; }));
    const { rerender } = render(<HandoffTab snap={snapshot()} viewer={viewer} />);
    api.getHandoffGate.mockResolvedValue({ ...readyGate, ok: false, reasons: ['New package not approved'] });
    rerender(<HandoffTab snap={snapshot({ approvalPackage: { id: 'new', sow_version_id: 'version', status: 'pending_delivery_hr' } })} viewer={viewer} />);
    expect(await screen.findByText('New package not approved')).toBeInTheDocument();
    await act(async () => resolve(readyGate));
    expect(screen.getByRole('button', { name: 'Release handoff' })).toBeDisabled();
    expect(screen.getByText('New package not approved')).toBeInTheDocument();
  });
});
