import React from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  FileAudio, 
  Clock, 
  Calendar,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Loader2
} from "lucide-react";
import { format } from 'date-fns';
import { cn } from "@/lib/utils";

const STATUS_CONFIG = {
  needs_upload: { color: 'bg-slate-200 text-slate-700', icon: AlertTriangle },
  uploaded: { color: 'bg-slate-100 text-slate-600', icon: FileAudio },
  created: { color: 'bg-slate-100 text-slate-600', icon: FileAudio },
  queued: { color: 'bg-blue-100 text-blue-700', icon: Loader2, spin: true },
  running: { color: 'bg-blue-100 text-blue-700', icon: Loader2, spin: true },
  succeeded: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  processing: { color: 'bg-blue-100 text-blue-700', icon: Loader2, spin: true },
  transcribed: { color: 'bg-amber-100 text-amber-700', icon: Clock },
  formalized: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  complete: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  failed: { color: 'bg-red-100 text-red-700', icon: AlertTriangle },
  partial: { color: 'bg-amber-100 text-amber-700', icon: AlertTriangle }
};

function formatDuration(seconds) {
  if (!seconds) return null;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins > 60) {
    const hrs = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hrs}h ${remainingMins}m`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export default function SessionCard({ 
  session, 
  onClick,
  isSelected,
  className 
}) {
  const statusConfig = STATUS_CONFIG[session.status] || STATUS_CONFIG.uploaded;
  const StatusIcon = statusConfig.icon;

  return (
    <Card 
      className={cn(
        "border-slate-200 cursor-pointer transition-all hover:border-slate-300 hover:shadow-sm",
        isSelected && "ring-2 ring-slate-400 border-slate-400",
        className
      )}
      onClick={() => onClick?.(session)}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-slate-800 truncate">
                {session.title || 'Untitled Session'}
              </h3>
              <Badge className={cn("text-xs flex-shrink-0", statusConfig.color)}>
                <StatusIcon className={cn("h-3 w-3 mr-1", statusConfig.spin && "animate-spin")} />
                {session.status}
              </Badge>
            </div>
            
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {format(new Date(session.created_date), 'MMM d, yyyy')}
              </span>
              {session.duration_seconds && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDuration(session.duration_seconds)}
                </span>
              )}
            </div>

            {session.audio_filename && (
              <p className="text-xs text-slate-400 mt-1 truncate">
                {session.audio_filename}
              </p>
            )}

            {session.tags?.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {session.tags.slice(0, 3).map(tag => (
                  <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                  </Badge>
                ))}
                {session.tags.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{session.tags.length - 3}
                  </Badge>
                )}
              </div>
            )}
          </div>

          <ChevronRight className="h-5 w-5 text-slate-400 flex-shrink-0" />
        </div>
      </CardContent>
    </Card>
  );
}
