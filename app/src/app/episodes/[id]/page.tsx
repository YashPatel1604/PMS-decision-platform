import { EpisodeDetailView } from "@/components/episodes-view";

export default async function EpisodeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EpisodeDetailView episodeId={Number(id)} />;
}
