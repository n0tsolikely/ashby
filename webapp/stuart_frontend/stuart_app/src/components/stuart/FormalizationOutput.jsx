import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  FileText, 
  Code, 
  Link2, 
  Download, 
  Printer,
  AlertTriangle,
  Trash2
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

export default function FormalizationOutput({ 
  formalization, 
  onHighlightSegments,
  onDownloadMarkdown,
  onDownloadText,
  onDownloadPdf,
  onPrintPdf,
  onRenameRun,
  onDeleteRun,
  className 
}) {
  const [activeTab, setActiveTab] = useState("formatted");
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');

  if (!formalization) {
    return (
      <Card className={cn("border-slate-200", className)}>
        <CardContent className="py-12 text-center">
          <FileText className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500">No formalization generated yet</p>
          <p className="text-sm text-slate-400 mt-1">
            Select a mode and template, then click "Run" to generate
          </p>
        </CardContent>
      </Card>
    );
  }

  const { output_json, output_markdown, evidence_map, status, mode, template, retention_level } = formalization;
  const runLabel = formalization.run_id || formalization.id;
  const titleLabel = (typeof formalization.title === 'string' && formalization.title.trim()) || `Formalization ${String(runLabel || '').replace(/^run_/, '').slice(0, 8)}`;
  const printUrl = formalization.pdf_url || output_json?.downloads?.primary?.pdf?.url || null;
  const textUrl = output_json?.downloads?.primary?.txt?.url || null;
  const isDevMode =
    ((typeof window !== 'undefined' && window.localStorage?.getItem('stuartDevMode') === '1') ||
      (typeof import.meta !== 'undefined' && import.meta?.env?.REACT_APP_DEVTOOLS === '1') ||
      (typeof process !== 'undefined' && process?.env?.REACT_APP_DEVTOOLS === '1'));

  const commitRename = () => {
    const next = renameDraft.trim();
    setIsRenaming(false);
    if (!next) return;
    if (next === (formalization?.title || '').trim()) return;
    onRenameRun?.(formalization, next);
  };

  return (
    <Card className={cn("border-slate-200", className)}>
      <CardHeader className="pb-3 border-b border-slate-100">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-base font-medium text-slate-700">
              {titleLabel}
            </CardTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="capitalize">
                {mode?.replace('_', ' ')}
              </Badge>
              <Badge variant="outline" className="text-xs">
                {template}
              </Badge>
              {runLabel && (
                <Badge variant="outline" className="text-xs">
                  Run {String(runLabel).replace(/^run_/, '').slice(0, 8)}
                </Badge>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 self-start md:self-auto">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDownloadMarkdown?.(formalization)}
              disabled={!output_markdown}
            >
              <Download className="h-4 w-4 mr-1.5" />
              Markdown
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDownloadText?.(formalization)}
              disabled={!textUrl}
            >
              <Download className="h-4 w-4 mr-1.5" />
              Text
            </Button>
            {printUrl && (
              <>
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => onPrintPdf?.(formalization)}
                >
                  <Printer className="h-4 w-4 mr-1.5" />
                  Print
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onDownloadPdf?.(formalization)}
                >
                  <Download className="h-4 w-4 mr-1.5" />
                  PDF
                </Button>
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRenameDraft(formalization?.title || '');
                setIsRenaming(true);
              }}
            >
              Rename
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDeleteRun?.(formalization)}
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              Delete
            </Button>
          </div>
        </div>
        {status === 'partial' && (
          <div className="flex items-center gap-2 mt-2 p-2 bg-amber-50 rounded-lg">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <span className="text-sm text-amber-700">
              Partial output - some sections may be incomplete
            </span>
          </div>
        )}
        {isRenaming && (
          <div className="mt-3 flex items-center gap-2">
            <Input
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.target.value)}
              maxLength={120}
              placeholder="Formalization title"
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename();
                if (e.key === 'Escape') setIsRenaming(false);
              }}
              onBlur={commitRename}
            />
          </div>
        )}
      </CardHeader>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <div className="px-4 pt-3 border-b border-slate-100">
          <TabsList className="bg-slate-100/50">
            <TabsTrigger value="formatted" className="text-sm">
              <FileText className="h-4 w-4 mr-1.5" />
              Formatted
            </TabsTrigger>
            <TabsTrigger value="markdown" className="text-sm">
              <FileText className="h-4 w-4 mr-1.5" />
              Markdown
            </TabsTrigger>
            {isDevMode && (
              <TabsTrigger value="json" className="text-sm">
                <Code className="h-4 w-4 mr-1.5" />
                JSON
              </TabsTrigger>
            )}
            {isDevMode && (
              <TabsTrigger value="evidence" className="text-sm">
                <Link2 className="h-4 w-4 mr-1.5" />
                Evidence Map
              </TabsTrigger>
            )}
          </TabsList>
        </div>

        <ScrollArea className="h-[500px]">
          <TabsContent value="formatted" className="p-4 mt-0">
            {output_markdown ? (
              <div className="prose prose-sm prose-slate max-w-none">
                <ReactMarkdown>{output_markdown}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-slate-400 italic">No formatted output available</p>
            )}
          </TabsContent>

          <TabsContent value="markdown" className="p-4 mt-0">
            {output_markdown ? (
              <pre className="p-4 bg-slate-900 text-slate-100 rounded-lg text-xs overflow-x-auto whitespace-pre-wrap">
                {output_markdown}
              </pre>
            ) : (
              <p className="text-slate-400 italic">No markdown output available</p>
            )}
          </TabsContent>

          {isDevMode && (
            <TabsContent value="json" className="p-4 mt-0">
              {output_json ? (
                <pre className="p-4 bg-slate-900 text-slate-100 rounded-lg text-xs overflow-x-auto">
                  {JSON.stringify(output_json, null, 2)}
                </pre>
              ) : (
                <p className="text-slate-400 italic">No JSON output available</p>
              )}
            </TabsContent>
          )}

          {isDevMode && (
            <TabsContent value="evidence" className="p-4 mt-0">
              {evidence_map && (Array.isArray(evidence_map) ? evidence_map.length > 0 : true) ? (
                <pre className="p-4 bg-slate-900 text-slate-100 rounded-lg text-xs overflow-x-auto">
                  {JSON.stringify(evidence_map, null, 2)}
                </pre>
              ) : (
                <div className="text-center py-8">
                  <Link2 className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-400">No evidence mapping available</p>
                </div>
              )}
            </TabsContent>
          )}
        </ScrollArea>
      </Tabs>

      <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/50">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Retention: {retention_level}</span>
          {formalization.data_left_machine && (
            <Badge variant="outline" className="text-amber-600 border-amber-300">
              Data sent externally
            </Badge>
          )}
        </div>
      </div>
    </Card>
  );
}
