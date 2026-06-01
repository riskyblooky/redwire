import api from './api';

/**
 * Build an authenticated evidence-download URL by first minting a
 * purpose-scoped 60s `evidence_dl` JWT via the backend, then
 * embedding it in the `?token=` query param. This keeps the user's
 * long-lived session JWT off URL sinks (browser history, proxy
 * logs, Referer headers). GHSA-gjcp-hxgm-2vx7.
 */
export async function getEvidenceDownloadUrl(evidenceId: string, cacheBust = false): Promise<string> {
    const { data } = await api.post(`/evidence/${evidenceId}/download-token`);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
    const bust = cacheBust ? `&t=${Date.now()}` : '';
    return `${apiUrl}/evidence/${evidenceId}/download?token=${data.token}${bust}`;
}
