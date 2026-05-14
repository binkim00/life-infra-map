import axios from 'axios'

const API_BASE_URL = 'http://127.0.0.1:8000/api'

export const getRecommendationTest = async (scenario = 'work_cafe') => {
  const response = await axios.get(`${API_BASE_URL}/recommendations/search/`, {
    params: {
      scenario,
    },
  })

  return response.data
}