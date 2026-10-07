import { useQuery } from '@tanstack/react-query'
import { getCatalog } from '../../api/endpoints'
import { queryKeys } from '../../api/queryKeys'
import { ShortId } from '../../components/controls/ShortId'
import { ListTable } from '../../components/data/ListTable'
import { PageHeader } from '../../components/layout/PageHeader'
import { LoadingRows } from '../../components/feedback/States'
import { formatDay, isDateText } from '../../lib/dates'
import { PageError } from '../shared'
import styles from './Catalog.module.css'

/**
 * The published datasets, one row each (spec UF-C01–C03). The Rows column
 * of the mock is left out: the catalog has no row counts (R32).
 */
export function Catalog() {
  const query = useQuery({ queryKey: queryKeys.catalog, queryFn: getCatalog })
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  const { datasets, publication, freshness } = query.data.data
  const latest = freshness.latest_observation_date
  const latestText = latest && isDateText(latest) ? formatDay(latest) : 'Unavailable'
  return <section>
    <PageHeader title="Catalog" subtitle={<>{datasets.length} tables{publication && <> in <ShortId value={publication.version_id} /></>}.</>} />
    <div className={styles.list}>
      <ListTable label="Datasets" rowHeight={52} columns={[{ header: 'Table', track: '1.3fr' }, { header: 'Dataset', track: '1.3fr' }, { header: 'Latest observation', track: '1fr' }]}
        rows={datasets.map((dataset) => ({ key: dataset.key, to: `/catalog/${dataset.key}`, link: dataset.key, cells: [<span key="label" className={styles.label}>{dataset.label}</span>, latestText] }))} />
    </div>
  </section>
}
