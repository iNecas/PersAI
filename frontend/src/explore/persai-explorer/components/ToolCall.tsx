import {
  Box,
  Stack,
  TextField,
  Card,
  CardContent,
  Typography,
  Collapse,
  IconButton,
} from "@mui/material";
import ChevronDownIcon from "mdi-material-ui/ChevronDown";
import ChevronUpIcon from "mdi-material-ui/ChevronUp";
import {
  TimeRangeValue,
  AbsoluteTimeRange,
  RelativeTimeRange,
  DatasourceSelector,
} from "@perses-dev/core";
import { Panel } from "@perses-dev/dashboards";

import {
  DataQueriesProvider,
  TimeRangeControls,
  TimeRangeProvider,
  useSuggestedStepMs,
} from "@perses-dev/plugin-system";

import { ReactElement, ReactNode, useState } from "react";

import useResizeObserver from "use-resize-observer";
import { ToolCall as ToolCallType } from "../types";

export interface TimeSeriesToolProps {
  query: string;
  timeRange: TimeRangeValue;
  datasource: DatasourceSelector;
  children?: ReactNode;
}

export interface ToolCallProps {
  toolCall: ToolCallType;
  datasource: DatasourceSelector;
}

const PANEL_PREVIEW_HEIGHT = 300;

/**
 * Renders a collapsible tool call display for unknown/generic tool types.
 * Shows the tool name by default, expandable to view arguments and results.
 */
export function GenericToolCall({
  toolCall,
}: {
  toolCall: ToolCallType;
}): ReactElement {
  const [expanded, setExpanded] = useState(false);

  const handleExpandClick = () => {
    setExpanded(!expanded);
  };

  return (
    <Box
      sx={{
        mt: 1,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        backgroundColor: "grey.100",
      }}
    >
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        sx={{
          px: 1.5,
          py: 0.5,
          cursor: "pointer",
          "&:hover": {
            backgroundColor: "grey.100",
          },
        }}
        onClick={handleExpandClick}
      >
        <Typography variant="caption" color="text.secondary" component="div">
          Tool: {toolCall.toolName}
        </Typography>
        <IconButton
          size="small"
          aria-expanded={expanded}
          aria-label="show more"
          sx={{ p: 0.25 }}
        >
          {expanded ? (
            <ChevronUpIcon fontSize="small" />
          ) : (
            <ChevronDownIcon fontSize="small" />
          )}
        </IconButton>
      </Box>

      <Collapse in={expanded} timeout="auto" unmountOnExit>
        <Box sx={{ p: 1.5, pt: 0 }}>
          {Object.keys(toolCall.args).length > 0 && (
            <>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                Arguments:
              </Typography>
              <Box
                component="pre"
                sx={{
                  backgroundColor: "grey.100",
                  p: 1,
                  borderRadius: 1,
                  fontSize: "0.75rem",
                  fontFamily: "monospace",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  mb: 1,
                  maxHeight: "150px",
                }}
              >
                {JSON.stringify(toolCall.args, null, 2)}
              </Box>
            </>
          )}

          {toolCall.result && (
            <>
              <Typography variant="caption" color="text.secondary" gutterBottom>
                Result:
              </Typography>
              <Box
                component="pre"
                sx={{
                  backgroundColor: "grey.100",
                  p: 1,
                  borderRadius: 1,
                  fontSize: "0.75rem",
                  fontFamily: "monospace",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: "150px",
                }}
              >
                {toolCall.result}
              </Box>
            </>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

/**
 * Renders a Prometheus time series query with an interactive chart and time range controls.
 * Displays the query in a read-only field and visualizes the results in a time series chart.
 */
export function TimeSeriesTool(props: TimeSeriesToolProps): ReactElement {
  const { width, ref: boxRef } = useResizeObserver();
  const { query, timeRange, datasource } = props;

  const height = PANEL_PREVIEW_HEIGHT;

  const definitions =
    query !== ""
      ? [
          {
            kind: "PrometheusTimeSeriesQuery",
            spec: {
              datasource: {
                kind: datasource.kind,
                name: datasource.name,
              },
              query: query,
            },
          },
        ]
      : [];

  const suggestedStepMs = useSuggestedStepMs(width);

  return (
    <Box
      ref={boxRef}
      height={height}
      sx={{
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      <TimeRangeProvider timeRange={timeRange} refreshInterval="0s">
        <DataQueriesProvider
          definitions={definitions}
          options={{ suggestedStepMs, mode: "range" }}
        >
          <Stack spacing={3} sx={{ height: "100%", p: 2 }}>
            <Stack direction="row" justifyContent="flex-end">
              <TimeRangeControls />
            </Stack>

            <TextField
              label="Query"
              value={query}
              variant="outlined"
              size="small"
              slotProps={{
                input: {
                  readOnly: true,
                },
              }}
              sx={{
                backgroundColor: "background.paper",
              }}
            />

            <Stack flexGrow={1}>
              <Panel
                panelOptions={{
                  hideHeader: true,
                }}
                definition={{
                  kind: "Panel",
                  spec: {
                    queries: [],
                    display: { name: "" },
                    plugin: {
                      kind: "TimeSeriesChart",
                      spec: {
                        visual: {
                          stack: "all",
                        },
                      },
                    },
                  },
                }}
              />
            </Stack>
          </Stack>
        </DataQueriesProvider>
      </TimeRangeProvider>
    </Box>
  );
}

/**
 * Main component that renders different tool call types based on the tool name.
 * Routes to specialized components for known tools or falls back to generic display.
 */
export function ToolCall({ toolCall, datasource }: ToolCallProps) {
  switch (toolCall.toolName) {
    case "execute_range_query":
      const { query, start, end } = toolCall.args;
      let timeRange: TimeRangeValue;
      if (start && end) {
        timeRange = {
          start: new Date(start),
          end: new Date(end),
        } as AbsoluteTimeRange;
      } else {
        timeRange = { pastDuration: duration || "1h" } as RelativeTimeRange;
      }

      return (
        <TimeSeriesTool
          query={query || ""}
          timeRange={timeRange}
          datasource={datasource}
        />
      );
    default:
      return <GenericToolCall toolCall={toolCall} />;
  }
}
