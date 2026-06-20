import { listProposals } from "../../lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const proposals = await listProposals();
    return Response.json({ proposals });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return Response.json({ error: message }, { status: 500 });
  }
}
