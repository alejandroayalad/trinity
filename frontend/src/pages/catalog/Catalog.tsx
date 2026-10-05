import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { getCatalog } from '../../api/endpoints'
import { queryKeys } from '../../api/queryKeys'
import { LoadingRows } from '../../components/feedback/States'
import { PageError } from '../shared'
export function Catalog() {
  const query = useQuery({ queryKey: queryKeys.catalog, queryFn: getCatalog })
  if (query.isPending) return <LoadingRows />
  if (query.error) return <PageError error={query.error} />
  return <section className="stack"><h1>Catalog</h1><p className="muted">Published datasets · Latest observation: {query.data.data.freshness.latest_observation_date ?? 'Unavailable'}</p><div className="panel table-scroll"><table><thead><tr><th>Dataset</th><th>Description</th></tr></thead><tbody>{query.data.data.datasets.map((dataset) => <tr key={dataset.key}><td><Link className="mono" to={`/catalog/${dataset.key}`}>{dataset.key}</Link><p>{dataset.label}</p></td><td>{dataset.description}</td></tr>)}</tbody></table></div></section>
}
