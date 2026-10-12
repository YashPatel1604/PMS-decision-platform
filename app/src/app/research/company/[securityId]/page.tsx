import { ResearchCompanyView } from "@/components/research-company-view";

export default async function ResearchCompanyPage({
  params,
}: {
  params: Promise<{ securityId: string }>;
}) {
  const { securityId } = await params;
  return <ResearchCompanyView securityId={decodeURIComponent(securityId)} />;
}
