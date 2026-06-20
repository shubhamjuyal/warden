import { listAudit } from "../../lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const audit = await listAudit();
    return Response.json(audit);
  } catch (e) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
