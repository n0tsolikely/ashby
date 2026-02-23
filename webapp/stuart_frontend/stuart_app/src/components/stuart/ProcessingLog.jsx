import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Loader2,
  Upload,
  Mic,
  FileText,
  Users,
  Zap,
  Shield
} from "lucide-react";
import { format } from 'date-fns';
import { cn } from "@/lib/utils";

const STEP_ICONS = {
  upload: Upload,
  transcribe: Mic,
  diarize: Users,
  align: FileText,
  formalize: Zap,
  render: FileText,
  security: Shield
};

const STATUS_CONFIG = {
  pending: { icon: Clock, color: 'text-slate-400', bg: 'bg-slate-100' },
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100', spin: true },
  completed: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100' },
  skipped: { icon: Clock, color: 'text-slate-300', bg: 'bg-slate-50' }
};

export default function ProcessingLog({ logs = [], className }) {
  if (!logs || logs.length === 0) {
    return null;
  }

  return (
    <Card className={cn("border-slate-200", className)}>
      <CardHeader className="pb-3 border-b border-slate-100">
        <CardTitle className="text-base font-medium text-slate-700">
          Processing Log
        </CardTitle>
      </CardHeader>

      <ScrollArea className="h-[300px]">
        <CardContent className="p-4">
          <div className="space-y-3">
            {logs.map((log, idx) => {
              const StepIcon = STEP_ICONS[log.step] || Zap;
              const statusConfig = STATUS_CONFIG[log.status] || STATUS_CONFIG.pending;
              const StatusIcon = statusConfig.icon;

              return (
                <div 
                  key={idx}
                  className={cn(
                    "flex items-start gap-3 p-3 rounded-lg",
                    statusConfig.bg
                  )}
                >
                  <div className="h-8 w-8 rounded-full bg-white flex items-center justify-center flex-shrink-0">
                    <StepIcon className="h-4 w-4 text-slate-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-slate-700 capitalize">
                        {log.step?.replace('_', ' ')}
                      </p>
                      <div className="flex items-center gap-1.5">
                        <StatusIcon 
                          className={cn(
                            "h-4 w-4",
                            statusConfig.color,
                            statusConfig.spin && "animate-spin"
                          )} 
                        />
                        <span className={cn("text-xs capitalize", statusConfig.color)}>
                          {log.status}
                        </span>
                      </div>
                    </div>
                    {log.message && (
                      <p className="text-sm text-slate-600 mt-1">
                        {log.message}
                      </p>
                    )}
                    {log.details && (
                      <div className="mt-2 space-y-1">
                        {Object.entries(log.details).map(([key, value]) => (
                          <div key={key} className="flex items-center gap-2 text-xs">
                            <span className="text-slate-500 capitalize">
                              {key.replace('_', ' ')}:
                            </span>
                            <span className="text-slate-700">{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {log.timestamp && (
                      <p className="text-xs text-slate-400 mt-1.5">
                        {format(new Date(log.timestamp), 'h:mm:ss a')}
                      </p>
                    )}
                    {log.data_sent_externally && (
                      <Badge variant="secondary" className="mt-2 text-xs text-amber-700 bg-amber-100">
                        <Shield className="h-3 w-3 mr-1" />
                        Data sent externally
                      </Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </ScrollArea>
    </Card>
  );
}