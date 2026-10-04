import { useQuery } from "@tanstack/react-query";
export type Round = { id: string; title: string; fixture_set: string; baseline: { objective: number; review: number; total: number }; selected: { objective: number; review: number; total: number }; comparison_valid: boolean; limitation: string };
export type LabEvent = { id: string; phase: string; summary: string; role: string; artifact_id: string };
export type Artifact = { artifact_id: string; title: string; category: string; summary: string };
export type LabState = { status: string; question: string; subject: {name:string;version:string}; orchestration:{name:string;interface:string;scope:string}; agents:{alias:string;role:string;turns:number[]}[]; resources:{alias:string;task:string;status:string}[]; rounds:Round[]; best:{accepted:null;observed:{round:string;objective:number;total:number};summary:string}; decision:string; next_action:string; learned:string[]; stop:{mode:string;summary:string}; artifacts:Artifact[]; pivot:{id:string;title:string;detail:string;status:string}[]; budget:{used:number;limit:number} };
async function get<T>(path:string):Promise<T>{const r=await fetch(path);if(!r.ok)throw new Error("Research summary unavailable");return r.json();}
export function useLab(){return {state:useQuery({queryKey:["public-lab"],queryFn:()=>get<LabState>("/api/lab")}),events:useQuery({queryKey:["public-events"],queryFn:()=>get<{events:LabEvent[]}>("/api/lab/events")})};}
export const evidenceUrl=(id:string)=>`/api/artifacts/${encodeURIComponent(id)}`;
