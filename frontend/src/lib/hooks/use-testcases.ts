import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface TestCase {
    custom_fields?: Record<string, unknown>;
    id: string;
    engagement_id: string;
    parent_id: string | null;
    title: string;
    category: string;
    description: string;
    steps: string | null;
    expected_result: string | null;
    actual_result: string | null;
    is_executed: boolean;
    is_successful: boolean | null;
    notes: string | null;
    classification_level?: string | null;
    classification_suffix?: string | null;
    created_at: string;
    updated_at: string;
    created_by: string;
    unresolved_thread_count?: number;
    created_by_username?: string;
    created_by_profile_photo?: string;
    findings?: { id: string; title: string; severity: string }[];
    vault_items?: { id: string; name: string; item_type: string }[];
    cleanup_artifacts?: { id: string; title: string; artifact_type: string; status: string }[];
    assets?: { id: string; name: string; asset_type: string; identifier: string }[];
    tags?: { id: string; name: string; color: string }[];
    evidence?: { id: string; original_filename: string; file_size: number; mime_type?: string; description?: string; include_in_report: boolean; created_at: string; created_by: string; created_by_username?: string; }[];
    attack_technique_ids?: string[];
}

export interface TestCaseCreate {
    custom_fields?: Record<string, unknown>;
    engagement_id: string;
    parent_id?: string | null;
    title: string;
    category: string;
    description: string;
    steps?: string;
    expected_result?: string;
    actual_result?: string;
    is_executed?: boolean;
    is_successful?: boolean | null;
    notes?: string;
    classification_level?: string | null;
    classification_suffix?: string | null;
    tag_ids?: string[];
    attack_technique_ids?: string[];
}

export interface TestCaseUpdate extends Partial<TestCaseCreate> {
    id: string;
}

export interface TestCaseTreeNode extends TestCase {
    children: TestCaseTreeNode[];
    depth: number;
}

/**
 * Build a tree structure from a flat list of test cases.
 * Returns only root nodes with nested children.
 */
export function buildTestCaseTree(testcases: TestCase[]): TestCaseTreeNode[] {
    const map = new Map<string, TestCaseTreeNode>();
    const roots: TestCaseTreeNode[] = [];

    // Create nodes
    for (const tc of testcases) {
        map.set(tc.id, { ...tc, children: [], depth: 0 });
    }

    // Build tree
    for (const tc of testcases) {
        const node = map.get(tc.id)!;
        if (tc.parent_id && map.has(tc.parent_id)) {
            const parent = map.get(tc.parent_id)!;
            node.depth = parent.depth + 1;
            parent.children.push(node);
        } else {
            roots.push(node);
        }
    }

    // Fix depths recursively for deeply nested trees
    function setDepths(nodes: TestCaseTreeNode[], depth: number) {
        for (const node of nodes) {
            node.depth = depth;
            setDepths(node.children, depth + 1);
        }
    }
    setDepths(roots, 0);

    return roots;
}

/**
 * Flatten a tree back into a list (in display order) for rendering.
 * Only includes nodes whose ancestors are all expanded.
 */
export function flattenTree(
    nodes: TestCaseTreeNode[],
    expandedIds: Set<string>
): TestCaseTreeNode[] {
    const result: TestCaseTreeNode[] = [];

    function walk(nodeList: TestCaseTreeNode[]) {
        for (const node of nodeList) {
            result.push(node);
            if (node.children.length > 0 && expandedIds.has(node.id)) {
                walk(node.children);
            }
        }
    }

    walk(nodes);
    return result;
}

// Fetch all test cases
export function useTestCases(engagementId?: string) {
    return useQuery({
        queryKey: engagementId ? ['testcases', 'engagement', engagementId] : ['testcases'],
        queryFn: async () => {
            const params = engagementId ? { engagement_id: engagementId } : {};
            const { data } = await api.get<TestCase[]>('/testcases', { params });
            return data;
        },
        staleTime: 30_000,
    });
}

// Fetch single test case
export function useTestCase(id: string) {
    return useQuery({
        queryKey: ['testcases', id],
        queryFn: async () => {
            const { data } = await api.get<TestCase>(`/testcases/${id}`);
            return data;
        },
        enabled: !!id,
        staleTime: 30_000,
    });
}

// Create test case
export function useCreateTestCase() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (testcase: TestCaseCreate) => {
            const { data } = await api.post<TestCase>('/testcases', testcase);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
            queryClient.invalidateQueries({ queryKey: ['testcases', 'engagement', data.engagement_id] });
        },
    });
}

// Update test case
export function useUpdateTestCase() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...testcase }: TestCaseUpdate) => {
            const { data } = await api.put<TestCase>(`/testcases/${id}`, testcase);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
            queryClient.invalidateQueries({ queryKey: ['testcases', data.id] });
            queryClient.invalidateQueries({ queryKey: ['testcases', 'engagement', data.engagement_id] });
            queryClient.invalidateQueries({ queryKey: ['versions', 'testcase', data.id] });
        },
    });
}

// Delete test case (with optional cascade to delete all children)
export function useDeleteTestCase() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, cascade = false }: { id: string; cascade?: boolean }) => {
            await api.delete(`/testcases/${id}`, { params: cascade ? { cascade: true } : {} });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

// Link a finding to a test case
export function useLinkFinding() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ testcaseId, findingId }: { testcaseId: string; findingId: string }) => {
            const { data } = await api.post(`/testcases/${testcaseId}/findings/${findingId}`);
            return data;
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['testcases', variables.testcaseId] });
            queryClient.invalidateQueries({ queryKey: ['findings', variables.findingId] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

// Unlink a finding from a test case
export function useUnlinkFinding() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ testcaseId, findingId }: { testcaseId: string; findingId: string }) => {
            const { data } = await api.delete(`/testcases/${testcaseId}/findings/${findingId}`);
            return data;
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['testcases', variables.testcaseId] });
            queryClient.invalidateQueries({ queryKey: ['findings', variables.findingId] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

// Link an asset to a test case
export function useLinkAsset() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ testcaseId, assetId, portIds }: { testcaseId: string; assetId: string; portIds?: string[] }) => {
            const params: any = {};
            if (portIds && portIds.length > 0) {
                params.port_ids = JSON.stringify(portIds);
            }
            const { data } = await api.post(`/testcases/${testcaseId}/assets/${assetId}`, null, { params });
            return data;
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['testcases', variables.testcaseId] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

// Unlink an asset from a test case
export function useUnlinkAsset() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ testcaseId, assetId }: { testcaseId: string; assetId: string }) => {
            const { data } = await api.delete(`/testcases/${testcaseId}/assets/${assetId}`);
            return data;
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['testcases', variables.testcaseId] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}
