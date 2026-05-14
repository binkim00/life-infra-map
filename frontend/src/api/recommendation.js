import axios from 'axios'

const API_BASE_URL = 'http://127.0.0.1:8000/api'

export const getRecommendations = async ({
  scenario = 'work_cafe',
  lat = 37.5665,
  lng = 126.9780,
}) => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/search/`, {
    params: {
      scenario,
      lat,
      lng,
    },
  })

  return response.data
}