import {useEffect, useState} from "react";
import {useHistory} from "react-router-dom";

export const useSearchParam = (key, defaultValue = null) => {
    // Get a window.location.search param.
    const startingValue = new URLSearchParams().get(key);

    const [value, setValue] = useState(startingValue || defaultValue);
    const history = useHistory();

    useEffect(() => {
        const params = new URLSearchParams();
        if (value) {
            params.append(key, value);
        } else {
            params.delete(key);
        }
        history.push({search: params.toString()});
    }, [value])

    return [value, setValue];
}
