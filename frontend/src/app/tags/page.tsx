/**
 * tags/page.tsx — Tag Management Page
 *
 * CRUD interface for colour-coded tags, split into two tabs:
 *
 * **Finding Tags** — tags applied to security findings for
 * categorisation across engagements.
 *
 * **Test Case Tags** — tags applied to test cases.
 *
 * Both tabs share the same data source (`useTags`) and feature:
 *  - Searchable tag table with colour swatch, name, and live badge
 *    preview.
 *  - Create dialog: name input, hex colour picker with 16 preset
 *    swatches, live badge preview.
 *  - Edit dialog: inline rename and colour change.
 *  - Delete with confirmation (warns about removal from linked items).
 *  - Permission-gated edit/delete actions via `useCanManageTags`.
 *  - Search results sorted by relevance (`relevanceComparator`).
 *
 * Hooks: `useTags`, `useCreateTag`, `useUpdateTag`, `useDeleteTag`,
 * `useCanManageTags`.
 */
'use client';

import { useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { useTags, useCreateTag, useUpdateTag, useDeleteTag, useCanManageTags, Tag } from '@/lib/hooks/use-tags';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { relevanceComparator } from '@/lib/search-relevance';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
    Tags as TagsIcon,
    Plus,
    Search,
    Pencil,
    Trash2,
    Loader2,
    Bug,
    ShieldAlert,
    Palette,
    FlaskConical,
} from 'lucide-react';

// ─── Color presets ───────────────────────────────────────────────
const COLOR_PRESETS = [
    { name: 'Red', value: '#ef4444' },
    { name: 'Orange', value: '#f97316' },
    { name: 'Amber', value: '#f59e0b' },
    { name: 'Yellow', value: '#eab308' },
    { name: 'Lime', value: '#84cc16' },
    { name: 'Emerald', value: '#10b981' },
    { name: 'Teal', value: '#14b8a6' },
    { name: 'Cyan', value: '#06b6d4' },
    { name: 'Blue', value: '#3b82f6' },
    { name: 'Indigo', value: '#6366f1' },
    { name: 'Violet', value: '#7c3aed' },
    { name: 'Purple', value: '#a855f7' },
    { name: 'Fuchsia', value: '#d946ef' },
    { name: 'Pink', value: '#ec4899' },
    { name: 'Rose', value: '#f43f5e' },
    { name: 'Slate', value: '#64748b' },
];


// ═══════════════════════════════════════════════════════════════════
// Main Tags Page
// ═══════════════════════════════════════════════════════════════════
export default function TagsPage() {
    const { user } = useAuthStore();
    const { data: canManage = false } = useCanManageTags();

    // ── Finding tags ──
    const { data: tags = [], isLoading } = useTags();
    const createTag = useCreateTag();
    const updateTag = useUpdateTag();
    const deleteTag = useDeleteTag();

    // ── UI state ──
    const [search, setSearch] = useState('');
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [editingTag, setEditingTag] = useState<Tag | null>(null);

    // ── Create form state ──
    const [newName, setNewName] = useState('');
    const [newColor, setNewColor] = useState('#3b82f6');

    // ── Edit form state ──
    const [editName, setEditName] = useState('');
    const [editColor, setEditColor] = useState('');

    const { confirm } = useConfirmDialog();

    // ── Filter tags ──
    const filteredTags = tags.filter(tag => {
        if (!search) return true;
        return tag.name.toLowerCase().includes(search.toLowerCase());
    }).sort(relevanceComparator(
        search,
        [tag => tag.name],
        (a, b) => a.name.localeCompare(b.name)
    ));

    // ── Handlers ──
    const handleCreate = async () => {
        if (!newName.trim()) return;
        try {
            await createTag.mutateAsync({ name: newName.trim(), color: newColor });
            toast.success('Tag created');
            setIsCreateOpen(false);
            setNewName('');
            setNewColor('#3b82f6');
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to create tag'));
        }
    };

    const handleUpdate = async () => {
        if (!editingTag || !editName.trim()) return;
        try {
            await updateTag.mutateAsync({ id: editingTag.id, name: editName.trim(), color: editColor });
            toast.success('Tag updated');
            setEditingTag(null);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to update tag'));
        }
    };

    const handleDelete = async (tag: Tag) => {
        const confirmed = await confirm({
            title: 'Delete Tag',
            description: `Are you sure you want to delete "${tag.name}"? It will be removed from all findings and test cases that use it.`,
        });
        if (!confirmed) return;
        try {
            await deleteTag.mutateAsync(tag.id);
            toast.success('Tag deleted');
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Failed to delete tag'));
        }
    };

    const openEdit = (tag: Tag) => {
        setEditName(tag.name);
        setEditColor(tag.color || '#3b82f6');
        setEditingTag(tag);
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
                                <TagsIcon className="h-6 w-6 text-primary" />
                            </div>
                            Tags
                        </h1>
                    </div>
                    {!canManage && (
                        <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1.5">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            View Only
                        </Badge>
                    )}
                </div>

                {/* Tabs */}
                <Tabs defaultValue="findings" className="space-y-4">
                    <TabsList className="bg-slate-800/50 border border-slate-700">
                        <TabsTrigger value="findings" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary gap-2">
                            <Bug className="h-4 w-4" />
                            Finding Tags
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{tags.length}</Badge>
                        </TabsTrigger>
                        <TabsTrigger value="testcases" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary gap-2">
                            <FlaskConical className="h-4 w-4" />
                            Test Case Tags
                            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">{tags.length}</Badge>
                        </TabsTrigger>
                    </TabsList>

                    {/* ─── Finding Tags Tab ─── */}
                    <TabsContent value="findings">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Finding Tags</CardTitle>
                                        <CardDescription>Tags for categorizing and labeling findings across engagements</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search tags..."
                                                value={search}
                                                onChange={e => setSearch(e.target.value)}
                                                className="pl-10 w-64 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        {canManage && (
                                            <Button
                                                onClick={() => setIsCreateOpen(true)}
                                                className="bg-primary hover:bg-primary/90 text-white gap-2"
                                            >
                                                <Plus className="h-4 w-4" />
                                                New Tag
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {isLoading ? (
                                    <div className="flex items-center justify-center py-12">
                                        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                                    </div>
                                ) : filteredTags.length === 0 ? (
                                    <div className="text-center py-12 text-slate-500">
                                        {search ? 'No tags match your search' : 'No tags created yet'}
                                    </div>
                                ) : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 hover:bg-transparent">
                                                    <TableHead className="text-slate-400 w-16">Color</TableHead>
                                                    <TableHead className="text-slate-400">Name</TableHead>
                                                    <TableHead className="text-slate-400 w-48">Preview</TableHead>
                                                    {canManage && (
                                                        <TableHead className="text-slate-400 w-32 text-right">Actions</TableHead>
                                                    )}
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredTags.map(tag => (
                                                    <TableRow key={tag.id} className="border-slate-800 hover:bg-slate-800/30">
                                                        <TableCell>
                                                            <div
                                                                className="h-6 w-6 rounded-full border border-slate-600"
                                                                style={{ backgroundColor: tag.color || '#64748b' }}
                                                            />
                                                        </TableCell>
                                                        <TableCell className="font-medium text-white">
                                                            {tag.name}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Badge
                                                                variant="outline"
                                                                className="text-xs border-none"
                                                                style={{
                                                                    backgroundColor: `${tag.color || '#64748b'}20`,
                                                                    color: tag.color || '#64748b',
                                                                }}
                                                            >
                                                                {tag.name}
                                                            </Badge>
                                                        </TableCell>
                                                        {canManage && (
                                                            <TableCell className="text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    <Button
                                                                        size="icon"
                                                                        variant="ghost"
                                                                        className="h-8 w-8 text-slate-400 hover:text-white"
                                                                        onClick={() => openEdit(tag)}
                                                                    >
                                                                        <Pencil className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                    <Button
                                                                        size="icon"
                                                                        variant="ghost"
                                                                        className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                                                        onClick={() => handleDelete(tag)}
                                                                    >
                                                                        <Trash2 className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                </div>
                                                            </TableCell>
                                                        )}
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ─── Test Case Tags Tab ─── */}
                    <TabsContent value="testcases">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <CardTitle className="text-white">Test Case Tags</CardTitle>
                                        <CardDescription>Tags for categorizing and labeling test cases across engagements</CardDescription>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                            <Input
                                                placeholder="Search tags..."
                                                value={search}
                                                onChange={e => setSearch(e.target.value)}
                                                className="pl-10 w-64 bg-slate-800/50 border-slate-700"
                                            />
                                        </div>
                                        {canManage && (
                                            <Button
                                                onClick={() => setIsCreateOpen(true)}
                                                className="bg-primary hover:bg-primary/90 text-white text-white gap-2"
                                            >
                                                <Plus className="h-4 w-4" />
                                                New Tag
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {isLoading ? (
                                    <div className="flex items-center justify-center py-12">
                                        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                                    </div>
                                ) : filteredTags.length === 0 ? (
                                    <div className="text-center py-12 text-slate-500">
                                        {search ? 'No tags match your search' : 'No tags created yet'}
                                    </div>
                                ) : (
                                    <div className="rounded-lg border border-slate-800 overflow-hidden">
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-slate-800 hover:bg-transparent">
                                                    <TableHead className="text-slate-400 w-16">Color</TableHead>
                                                    <TableHead className="text-slate-400">Name</TableHead>
                                                    <TableHead className="text-slate-400 w-48">Preview</TableHead>
                                                    {canManage && (
                                                        <TableHead className="text-slate-400 w-32 text-right">Actions</TableHead>
                                                    )}
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {filteredTags.map(tag => (
                                                    <TableRow key={tag.id} className="border-slate-800 hover:bg-slate-800/30">
                                                        <TableCell>
                                                            <div
                                                                className="h-6 w-6 rounded-full border border-slate-600"
                                                                style={{ backgroundColor: tag.color || '#64748b' }}
                                                            />
                                                        </TableCell>
                                                        <TableCell className="font-medium text-white">
                                                            {tag.name}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Badge
                                                                variant="outline"
                                                                className="text-xs border-none"
                                                                style={{
                                                                    backgroundColor: `${tag.color || '#64748b'}20`,
                                                                    color: tag.color || '#64748b',
                                                                }}
                                                            >
                                                                {tag.name}
                                                            </Badge>
                                                        </TableCell>
                                                        {canManage && (
                                                            <TableCell className="text-right">
                                                                <div className="flex items-center justify-end gap-1">
                                                                    <Button
                                                                        size="icon"
                                                                        variant="ghost"
                                                                        className="h-8 w-8 text-slate-400 hover:text-white"
                                                                        onClick={() => openEdit(tag)}
                                                                    >
                                                                        <Pencil className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                    <Button
                                                                        size="icon"
                                                                        variant="ghost"
                                                                        className="h-8 w-8 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                                                        onClick={() => handleDelete(tag)}
                                                                    >
                                                                        <Trash2 className="h-3.5 w-3.5" />
                                                                    </Button>
                                                                </div>
                                                            </TableCell>
                                                        )}
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </div>

            {/* ─── Create Dialog ─── */}
            <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 max-w-md">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Plus className="h-5 w-5 text-primary" />
                            Create Tag
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label className="text-slate-300">Name</Label>
                            <Input
                                value={newName}
                                onChange={e => setNewName(e.target.value)}
                                placeholder="e.g. SQL Injection, OWASP Top 10..."
                                className="bg-slate-800 border-slate-700"
                                onKeyDown={e => e.key === 'Enter' && handleCreate()}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 flex items-center gap-2">
                                <Palette className="h-4 w-4" />
                                Color
                            </Label>
                            <div className="flex items-center gap-3">
                                <input
                                    type="color"
                                    value={newColor}
                                    onChange={e => setNewColor(e.target.value)}
                                    className="h-10 w-10 rounded cursor-pointer border border-slate-600 bg-transparent"
                                />
                                <Input
                                    value={newColor}
                                    onChange={e => setNewColor(e.target.value)}
                                    placeholder="#3b82f6"
                                    className="bg-slate-800 border-slate-700 font-mono text-sm w-28"
                                />
                                <Badge
                                    variant="outline"
                                    className="text-xs border-none ml-auto"
                                    style={{
                                        backgroundColor: `${newColor}20`,
                                        color: newColor,
                                    }}
                                >
                                    {newName || 'Preview'}
                                </Badge>
                            </div>
                            <div className="flex flex-wrap gap-1.5 pt-1">
                                {COLOR_PRESETS.map(preset => (
                                    <button
                                        key={preset.value}
                                        onClick={() => setNewColor(preset.value)}
                                        className={`h-6 w-6 rounded-full border-2 transition-all hover:scale-110 ${newColor === preset.value ? 'border-white scale-110' : 'border-transparent'
                                            }`}
                                        style={{ backgroundColor: preset.value }}
                                        title={preset.name}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setIsCreateOpen(false)} className="text-slate-400">
                            Cancel
                        </Button>
                        <Button
                            onClick={handleCreate}
                            disabled={!newName.trim() || createTag.isPending}
                            className="bg-primary hover:bg-primary/90 text-white"
                        >
                            {createTag.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Create Tag
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* ─── Edit Dialog ─── */}
            <Dialog open={!!editingTag} onOpenChange={(open) => !open && setEditingTag(null)}>
                <DialogContent className="bg-slate-900 border-slate-800 max-w-md">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Pencil className="h-5 w-5 text-primary" />
                            Edit Tag
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label className="text-slate-300">Name</Label>
                            <Input
                                value={editName}
                                onChange={e => setEditName(e.target.value)}
                                className="bg-slate-800 border-slate-700"
                                onKeyDown={e => e.key === 'Enter' && handleUpdate()}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 flex items-center gap-2">
                                <Palette className="h-4 w-4" />
                                Color
                            </Label>
                            <div className="flex items-center gap-3">
                                <input
                                    type="color"
                                    value={editColor}
                                    onChange={e => setEditColor(e.target.value)}
                                    className="h-10 w-10 rounded cursor-pointer border border-slate-600 bg-transparent"
                                />
                                <Input
                                    value={editColor}
                                    onChange={e => setEditColor(e.target.value)}
                                    placeholder="#3b82f6"
                                    className="bg-slate-800 border-slate-700 font-mono text-sm w-28"
                                />
                                <Badge
                                    variant="outline"
                                    className="text-xs border-none ml-auto"
                                    style={{
                                        backgroundColor: `${editColor}20`,
                                        color: editColor,
                                    }}
                                >
                                    {editName || 'Preview'}
                                </Badge>
                            </div>
                            <div className="flex flex-wrap gap-1.5 pt-1">
                                {COLOR_PRESETS.map(preset => (
                                    <button
                                        key={preset.value}
                                        onClick={() => setEditColor(preset.value)}
                                        className={`h-6 w-6 rounded-full border-2 transition-all hover:scale-110 ${editColor === preset.value ? 'border-white scale-110' : 'border-transparent'
                                            }`}
                                        style={{ backgroundColor: preset.value }}
                                        title={preset.name}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setEditingTag(null)} className="text-slate-400">
                            Cancel
                        </Button>
                        <Button
                            onClick={handleUpdate}
                            disabled={!editName.trim() || updateTag.isPending}
                            className="bg-primary hover:bg-primary/90 text-white"
                        >
                            {updateTag.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Save Changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </DashboardLayout>
    );
}
