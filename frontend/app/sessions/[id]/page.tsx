import { LiveSessionDetail } from '@/components/LiveSessionDetail'

export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return <LiveSessionDetail liveId={id} />
}
