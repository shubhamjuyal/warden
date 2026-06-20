import { listProposals } from "../../lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const proposals = await listProposals();
    return Response.json({ proposals });
  } catch (e) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
