import { useQuery } from "@tanstack/react-query";

type TraceNode = {
  id: string;
  title: string;
  summary: string;
  status?: string;
  observed_best?: string;
  accepted_best?: string | null;
};
type Trace = { scope: string; nodes: TraceNode[] };

export function TechnicalTrace() {
  const trace = useQuery({
    queryKey: ["public-technical-trace"],
    queryFn: async (): Promise<Trace> => {
      const response = await fetch("/api/technical-trace");
      if (!response.ok) throw new Error("Published trace unavailable");
      return response.json();
    },
  });
  return (
    <details className="technical-trace" id="technical-trace">
      <summary>
        <span><span className="section-kicker">FROM CANDIDATES TO THE NEXT DECISION</span><strong>Technical trace</strong></span>
        <span className="trace-toggle">Open the real chain <span aria-hidden="true">＋</span></span>
      </summary>
      <div className="trace-body">
        <p className="trace-scope">{trace.data?.scope ?? "Reviewed, anonymized summaries of the recorded research chain."}</p>
        {trace.isPending && <p>Loading the published trace…</p>}
        {trace.error && <p>The published trace is unavailable. No missing evidence is substituted.</p>}
        <ol className="trace-nodes">
          {trace.data?.nodes.map((node, index) => (
            <li key={node.id} data-trace-node={node.id}>
              <span className="trace-number">{String(index + 1).padStart(2, "0")}</span>
              <article>
                <div className="trace-node-heading"><h3>{node.title}</h3>{node.status && <span>{node.status.replaceAll("_", " ")}</span>}</div>
                <p>{node.summary}</p>
                {(node.observed_best !== undefined || node.accepted_best !== undefined) && <dl className="trace-best">
                  {node.observed_best !== undefined && <div><dt>Best observed</dt><dd>{node.observed_best}</dd></div>}
                  {node.accepted_best !== undefined && <div><dt>Best accepted</dt><dd>{node.accepted_best ?? "None · best_accepted: null"}</dd></div>}
                </dl>}
              </article>
            </li>
          ))}
        </ol>
        <p className="small-note">This is a safe display projection, not a terminal transcript. The research roles used an allowlisted evidence reader; this run does not establish unrestricted browsing or code editing.</p>
      </div>
    </details>
  );
}
