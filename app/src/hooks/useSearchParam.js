import {useEffect, useState} from "react";
import {useHistory} from "react-router-dom";

export const useSearchParam = (name, defaultValue = null) => {
    // Get a window.location.search param.
    const startingValue = new URLSearchParams().get(name);

    const [value, setValue] = useState(startingValue || defaultValue);
    const history = useHistory();

    useEffect(() => {
        const params = new URLSearchParams();
        if (value) {
            params.append(name, value);
        } else {
            params.delete(name);
        }
        history.push({search: params.toString()});
    }, [value, history])

    return [value, setValue];
}
